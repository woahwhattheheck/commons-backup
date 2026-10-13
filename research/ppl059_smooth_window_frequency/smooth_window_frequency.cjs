"use strict";
// Finite smooth-window frequency certificate. Classical construction; see API guide.
const VERSION="1.0.0";
function integer(x,min,max,name){if(!Number.isSafeInteger(x)||x<min||x>max)throw Error(name+" out of range");return x;}
function natural(x,name){if(typeof x==="number"){integer(x,0,Number.MAX_SAFE_INTEGER,name);return BigInt(x);}if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>1200)throw Error(name+" must be a natural decimal string");return BigInt(x);}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function word(mask,n){let s="";for(let i=n-1;i>=0;i--)s+=((mask>>i)&1)?"2":"1";return s;}
function encode(s){if(typeof s!=="string"||!/^[12]+$/.test(s)||s.length>16)throw Error("word must have 1..16 symbols in {1,2}");let m=0;for(const c of s)m=2*m+(c==="2"?1:0);return m;}
function ones(mask,n){let c=n;while(mask){c-=mask&1;mask>>>=1;}return c;}
function packFailure(mask,length,depth,start,run){return 1+mask+65536*(length+32*(depth+32*(start+32*run)));}
function unpackFailure(token){let t=token-1;const mask=t%65536;t=Math.floor(t/65536);const length=t%32;t=Math.floor(t/32);const depth=t%32;t=Math.floor(t/32);const start=t%32;const run=Math.floor(t/32);return {depth,derivative:word(mask,length),run_start:start,run_length:run};}
function smoothRecord(s,stats){const chain=[s];let depth=0;while(s.length){stats.derivative_levels++;const runs=[];let start=0;while(start<s.length){let end=start+1;while(end<s.length&&s[end]===s[start])end++;if(end-start>2){return {failure:packFailure(encode(s),s.length,depth,start,end-start),chain:null};}runs.push(end-start);start=end;}if(runs.length&&runs[0]===1)runs.shift();if(runs.length&&runs[runs.length-1]===1)runs.pop();s=runs.join("");chain.push(s);depth++;if(depth>31)throw Error("derivative depth cap");}return {failure:0,chain};}
function compileSmoothWindows(input){
 if(!input||typeof input!=="object")throw Error("input required");
 const n=integer(input.window_length,4,16,"window_length"),universe=2**n,half=2**(n-1);
 const stats={windows:universe,derivative_levels:0,karp_cells:0,karp_arc_relaxations:0,potential_passes:0,potential_arc_relaxations:0,dual_residuals:0,complement_edges:0,cycle_edges:0};
 const failures=new Array(universe),allowed=[],chains=[];
 for(let mask=0;mask<universe;mask++){const r=smoothRecord(word(mask,n),stats);failures[mask]=r.failure;if(!r.failure){allowed.push(mask);chains.push(r.chain);}}
 const masks=Array.from(new Set(allowed.flatMap(m=>[Math.floor(m/2),m%(half)]))).sort((a,b)=>a-b),N=masks.length;
 if(!N||N>2400)throw Error("node cap");const nodeOf=new Map(masks.map((m,i)=>[m,i]));
 const edges=allowed.map((m,id)=>({id,window:m,from:nodeOf.get(Math.floor(m/2)),to:nodeOf.get(m%half),symbol:(m&1)+1,weight:1-(m&1)}));
 const incoming=Array.from({length:N},()=>[]),outgoing=Array.from({length:N},()=>[]);
 for(const e of edges){incoming[e.to].push(e.id);outgoing[e.from].push(e.id);}
 const neg=-1000000000,dp=[new Int32Array(N)];stats.karp_cells=(N+1)*N;
 for(let k=1;k<=N;k++){const row=new Int32Array(N);row.fill(neg);for(const e of edges){stats.karp_arc_relaxations++;if(dp[k-1][e.from]>neg)row[e.to]=Math.max(row[e.to],dp[k-1][e.from]+e.weight);}dp.push(row);}
 let best=null;const candidates=[];
 for(let v=0;v<N;v++){if(dp[N][v]===neg)continue;let low=null,at=-1;for(let k=0;k<N;k++){if(dp[k][v]===neg)continue;const a=dp[N][v]-dp[k][v],b=N-k;if(low===null||a*low[1]<low[0]*b){low=[a,b];at=k;}}if(low){const g=gcd(Math.abs(low[0]),low[1]);low=[low[0]/g,low[1]/g];candidates.push({node:v,numerator:low[0],denominator:low[1],minimizing_length:at});if(best===null||low[0]*best[1]>best[0]*low[1])best=low;}}
 if(!best)throw Error("no cycle candidate");const [p,q]=best,H=new Array(N).fill(0);
 for(let pass=0;pass<N-1;pass++){let change=false;stats.potential_passes++;for(const e of edges){stats.potential_arc_relaxations++;const x=H[e.from]+q*e.weight-p;if(x>H[e.to]){H[e.to]=x;change=true;}}if(!change)break;}
 const residuals=edges.map(e=>{stats.dual_residuals++;const r=H[e.to]-H[e.from]-(q*e.weight-p);if(r<0)throw Error("candidate has positive reduced cycle or incomplete dual");return r;});
 const colors=new Uint8Array(N),parentNode=new Int32Array(N),parentEdge=new Int32Array(N);parentNode.fill(-1);parentEdge.fill(-1);let cycle=null;
 for(let start=0;start<N&&!cycle;start++){if(colors[start])continue;colors[start]=1;const stack=[{v:start,j:0}];while(stack.length&&!cycle){const frame=stack[stack.length-1];if(frame.j===outgoing[frame.v].length){colors[frame.v]=2;stack.pop();continue;}const eid=outgoing[frame.v][frame.j++];if(residuals[eid]!==0)continue;const e=edges[eid],v=e.to;if(!colors[v]){colors[v]=1;parentNode[v]=frame.v;parentEdge[v]=eid;stack.push({v,j:0});}else if(colors[v]===1){const rev=[];let u=frame.v;while(u!==v){if(u<0)throw Error("cycle backtrack");rev.push(parentEdge[u]);u=parentNode[u];}cycle=rev.reverse().concat(eid);}}}
 if(!cycle||!cycle.length)throw Error("no tight cycle");let weight=0;for(let i=0;i<cycle.length;i++){const e=edges[cycle[i]],next=edges[cycle[(i+1)%cycle.length]];if(e.to!==next.from)throw Error("cycle continuity");weight+=e.weight;stats.cycle_edges++;}
 if(q*weight!==p*cycle.length)throw Error("cycle mean mismatch");
 const complementNodes=masks.map(m=>nodeOf.get(half-1-m)),edgeOf=new Map(edges.map(e=>[e.window,e.id]));
 const complementEdges=edges.map(e=>{const j=edgeOf.get(universe-1-e.window);if(j===undefined||edges[j].from!==complementNodes[e.from]||edges[j].to!==complementNodes[e.to]||edges[j].weight!==1-e.weight)throw Error("complement closure");stats.complement_edges++;return j;});
 const maxH=Math.max(...H),B=Math.max(...masks.map((m,i)=>q*ones(m,n-1)-p*(n-1)-H[i]))+maxH;
 const cycleWord=cycle.map(id=>String(edges[id].symbol)).join("");
 const snapshot={schema:"commons.smooth_window_frequency/v1",version:VERSION,window_length:n,universe,failures,allowed,derivative_chains:chains,nodes:masks.map((m,id)=>({id,mask:m,word:word(m,n-1),ones:ones(m,n-1),complement:complementNodes[id]})),edges,incoming,outgoing,complement_edges:complementEdges,maximum_mean:{numerator:p,denominator:q},minimum_mean:{numerator:q-p,denominator:q},potential:H,dual_residuals:residuals,prefix_slack:B,critical_cycle:{edge_ids:cycle,period:cycleWord,length:cycle.length,ones:weight,start_node:edges[cycle[0]].from},candidate_rows:candidates,statistics:stats};
 return {snapshot,summary:{window_length:n,universe,allowed_windows:allowed.length,rejected_windows:universe-allowed.length,nodes:N,edges:edges.length,maximum_mean:snapshot.maximum_mean,minimum_mean:snapshot.minimum_mean,prefix_slack:B,critical_period:cycleWord,statistics:stats}};
}
function openSmoothWindows(snapshot){
 const s=snapshot;if(!s||s.schema!=="commons.smooth_window_frequency/v1"||s.version!==VERSION)throw Error("snapshot schema/version");
 const n=integer(s.window_length,4,16,"snapshot length"),universe=2**n,N=s.nodes.length;
 if(s.universe!==universe||!Array.isArray(s.failures)||s.failures.length!==universe||!Array.isArray(s.allowed)||s.allowed.length!==s.edges.length||s.derivative_chains.length!==s.allowed.length||s.potential.length!==N||s.dual_residuals.length!==s.edges.length||s.complement_edges.length!==s.edges.length)throw Error("snapshot shape");
 integer(s.maximum_mean.numerator,0,N,"mean numerator");integer(s.maximum_mean.denominator,1,N,"mean denominator");integer(s.prefix_slack,0,1000000000,"prefix slack");
 for(let i=0;i<s.failures.length;i++)integer(s.failures[i],0,2**40,"classification");
 for(let i=0;i<s.allowed.length;i++){integer(s.allowed[i],0,universe-1,"allowed window");if(i&&s.allowed[i]<=s.allowed[i-1])throw Error("window order");}
 for(let i=0;i<N;i++){if(s.nodes[i].id!==i)throw Error("node IDs");integer(s.potential[i],0,1000000000,"potential");}
 for(let i=0;i<s.edges.length;i++){const e=s.edges[i];if(e.id!==i||e.window!==s.allowed[i])throw Error("edge IDs");integer(e.from,0,N-1,"edge from");integer(e.to,0,N-1,"edge to");integer(e.symbol,1,2,"edge symbol");}
 const index=new Map(s.allowed.map((m,i)=>[m,i])),stats={queries:0,classification_lookups:0,graph_lookups:0,emitted_symbols:0,bound_queries:0,new_derivatives:0,new_graph_construction:0,new_cycle_optimization:0,new_dual_checks:0};
 const copy=x=>JSON.parse(JSON.stringify(x)),page=(a,offset,limit)=>{integer(offset,0,a.length,"offset");integer(limit,0,256,"limit");return {offset,total:a.length,items:copy(a.slice(offset,offset+limit)),next:Math.min(a.length,offset+limit)};};
 function classify(w){if(typeof w!=="string"||w.length!==n)throw Error("window length");const mask=encode(w),token=s.failures[mask];stats.classification_lookups++;if(token)return {word:w,mask,accepted:false,failure:unpackFailure(token)};const rank=index.get(mask);if(rank===undefined)throw Error("incomplete saved accepted index");return {word:w,mask,accepted:true,rank,derivative_chain:copy(s.derivative_chains[rank]),edge:copy(s.edges[rank])};}
 return {
 summary(){stats.queries++;return {window_length:n,universe,allowed_windows:s.allowed.length,nodes:N,edges:s.edges.length,maximum_mean:copy(s.maximum_mean),minimum_mean:copy(s.minimum_mean),prefix_slack:s.prefix_slack,critical_cycle:copy(s.critical_cycle),scope:"exact finite smooth-window shift; Kolakoski containment premise only"};},
 classifyWindow(w){stats.queries++;return classify(w);},
 selectWindow(rank){stats.queries++;integer(rank,0,s.allowed.length-1,"rank");return classify(word(s.allowed[rank],n));},
 windowsPage(offset=0,limit=32){stats.queries++;return page(s.allowed.map((mask,rank)=>({rank,mask,word:word(mask,n)})),offset,limit);},
 nodesPage(offset=0,limit=32){stats.queries++;return page(s.nodes,offset,limit);},
 edgesPage(offset=0,limit=32){stats.queries++;return page(s.edges,offset,limit);},
 potentialPage(offset=0,limit=32){stats.queries++;return page(s.potential.map((value,node)=>({node,value})),offset,limit);},
 frequencyBounds(length){stats.queries++;stats.bound_queries++;const T=natural(length,"length");if(T<BigInt(n-1))return {length:T.toString(),ones_min:"0",ones_max:T.toString(),reason:"below retained node length"};const p=BigInt(s.maximum_mean.numerator),q=BigInt(s.maximum_mean.denominator),B=BigInt(s.prefix_slack),lower=(q-p)*T-B,upper=p*T+B;let lo=lower<=0n?0n:(lower+q-1n)/q,hi=upper/q;if(hi>T)hi=T;return {length:T.toString(),ones_min:lo.toString(),ones_max:hi.toString(),asymptotic_lower:copy(s.minimum_mean),asymptotic_upper:copy(s.maximum_mean),slack_numerator:s.prefix_slack,denominator:s.maximum_mean.denominator,includes_all_Kolakoski_prefixes_under_stated_containment:true};},
 periodicWord(length,offset="0",complement=false){stats.queries++;integer(length,0,4096,"length");const phase=natural(offset,"offset")%BigInt(s.critical_cycle.length);let out="";for(let i=0;i<length;i++){const c=s.critical_cycle.period[(Number(phase)+i)%s.critical_cycle.length];out+=complement?(c==="1"?"2":"1"):c;}stats.emitted_symbols+=length;return {word:out,length,offset:String(offset),phase:phase.toString(),complement,period:complement?s.critical_cycle.period.replace(/[12]/g,c=>c==="1"?"2":"1"):s.critical_cycle.period,scope:"periodic extremizer of finite window graph; not identified as Kolakoski"};},
 traceWord(w){stats.queries++;if(typeof w!=="string"||w.length<n||w.length>4096||!/^[12]+$/.test(w))throw Error("trace word length/alphabet");let mask=encode(w.slice(0,n)),oneCount=0;for(const c of w)if(c==="1")oneCount++;const edge_ids=[];for(let pos=0;pos<=w.length-n;pos++){if(pos)mask=(mask%(universe/2))*2+(w[pos+n-1]==="2"?1:0);stats.graph_lookups++;const eid=index.get(mask);if(eid===undefined)return {accepted:false,first_bad_offset:pos,window:word(mask,n),failure:unpackFailure(s.failures[mask]),ones:oneCount};edge_ids.push(eid);}const start=s.edges[edge_ids[0]].from,end=s.edges[edge_ids[edge_ids.length-1]].to,p=s.maximum_mean.numerator,q=s.maximum_mean.denominator,edgeOnes=oneCount-s.nodes[start].ones;return {accepted:true,length:w.length,ones:oneCount,start_node:start,end_node:end,edge_ids,reduced_weight:q*edgeOnes-p*edge_ids.length,potential_difference:s.potential[end]-s.potential[start]};},
 statistics(){return copy(stats);}
 };
}
module.exports={VERSION,compileSmoothWindows,openSmoothWindows};
