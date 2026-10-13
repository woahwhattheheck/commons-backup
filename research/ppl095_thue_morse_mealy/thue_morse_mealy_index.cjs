"use strict";

/* Pure finite-state calculations; no I/O or external dependencies. */
const THUE_MORSE_MEALY_LIMITS = Object.freeze({
  max_states: 2,
  max_kernel_states: 512,
  max_snapshot_chars: 16000000,
  max_distinguishing_pairs: 262144,
  max_query_decimal_digits: 2048,
  max_difference_states: 4096,
  max_page_size: 256
});
const SCHEMA="commons.thue_morse_mealy_atlas/v1";
function need(ok,message) {if(!ok)throw new TypeError(message);}
function integer(x,lo,hi,name) {
  need(Number.isSafeInteger(x)&&x>=lo&&x<=hi,name+" is outside its integer range");
  return x;
}
function clone(x) {return JSON.parse(JSON.stringify(x));}
function natural(x,name) {
  if(typeof x==="bigint") {
    need(x>=0n,name+" must be nonnegative");
    need(x.toString().length<=THUE_MORSE_MEALY_LIMITS.max_query_decimal_digits,name+" exceeds the decimal bound");
    return x;
  }
  if(typeof x==="number") {need(Number.isSafeInteger(x)&&x>=0,name+" must be exact");return BigInt(x);}
  need(typeof x==="string"&&x.length<=THUE_MORSE_MEALY_LIMITS.max_query_decimal_digits&&/^(0|[1-9][0-9]*)$/.test(x),name+" must be a bounded canonical decimal");
  return BigInt(x);
}
function functionSystem(q) {
  const count=q**q,mappings=[];
  for(let code=0;code<count;code++) {
    let x=code;const row=[];
    for(let s=0;s<q;s++){row.push(x%q);x=Math.floor(x/q);}
    mappings.push(row);
  }
  const compositions=Array.from({length:count},()=>Array(count));
  for(let f=0;f<count;f++)for(let g=0;g<count;g++) {
    let code=0,power=1;
    for(let s=0;s<q;s++){code+=mappings[f][mappings[g][s]]*power;power*=q;}
    compositions[f][g]=code;
  }
  let identity=0,power=1;
  for(let s=0;s<q;s++){identity+=s*power;power*=q;}
  return {count,mappings,compositions,identity};
}
function nextKernel(state,digit,composition) {
  const [f0,f1,g0,g1,p]=state;
  return [
    composition[f1][f0],composition[f0][f1],
    digit?composition[g1][f0]:g0,
    digit?composition[g0][f1]:g1,
    p^digit
  ];
}
function stateKey(state) {return state.join(",");}
function outputBit(code,qstate,parity) {return (code>>>(2*qstate+parity))&1;}

/**
 * Enumerate one or two labelled states, start state zero and one output bit
 * for every input bit. Machine tables with unreachable states remain distinct.
 */
function compileThueMorseMealyAtlas(input={state_count:2}) {
  need(input&&typeof input==="object","input must be an object");
  const q=integer(input.state_count,1,THUE_MORSE_MEALY_LIMITS.max_states,"state_count");
  const cap=integer(input.max_kernel_states===undefined?THUE_MORSE_MEALY_LIMITS.max_kernel_states:input.max_kernel_states,1,THUE_MORSE_MEALY_LIMITS.max_kernel_states,"max_kernel_states");
  const funcs=functionSystem(q),M=funcs.count,transitionCount=M*M,outputCount=2**(2*q);
  const kernels=[],classes=[],machines=[],classByKey=new Map();
  const counters={
    function_mappings:M,function_compositions:M*M,
    kernel_graphs:0,kernel_states:0,kernel_edges:0,
    output_assignments:0,minimizations:0,refinement_rounds:0,
    original_distinguishing_pairs:0,retained_distinguishing_pairs:0,
    quotient_map_entries:0,machine_tables:0,
    input_stream_symbols_expanded:0
  };
  function incomplete(message,extra) {
    const error=new RangeError(message);error.code="ATLAS_BUDGET";
    error.partial={status:"INCOMPLETE",state_count:q,kernels:clone(kernels),
      classes:clone(classes),machines:clone(machines),counters:clone(counters),...extra};
    throw error;
  }
  for(let transition=0;transition<transitionCount;transition++) {
    const f0=transition%M,f1=Math.floor(transition/M);
    const states=[[f0,f1,funcs.identity,funcs.identity,0]],edges=[],seen=new Map([[stateKey(states[0]),0]]);
    for(let i=0;i<states.length;i++) {
      const row=[];
      for(let digit=0;digit<2;digit++) {
        const next=nextKernel(states[i],digit,funcs.compositions),key=stateKey(next);
        let id=seen.get(key);
        if(id===undefined) {
          if(states.length>=cap)incomplete("kernel state cap reached",{
            unfinished_transition_code:transition,unfinished_kernel_states:clone(states),
            unfinished_kernel_edges:clone(edges),current_state:i,current_digit:digit
          });
          id=states.length;seen.set(key,id);states.push(next);
        }
        row.push(id);counters.kernel_edges++;
      }
      edges.push(row);
    }
    kernels.push({transition_code:transition,delta_functions:[f0,f1],root:0,states,transitions:edges});
    counters.kernel_graphs++;counters.kernel_states+=states.length;
  }
  function minimize(kernel,outputs) {
    const n=outputs.length,words=Array.from({length:n},()=>Array(n).fill(null));
    for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)if(outputs[i]!==outputs[j]) {
      words[i][j]=words[j][i]="";counters.original_distinguishing_pairs++;
    }
    let partition=outputs.slice(),rounds=0;
    while(true) {
      const groups=new Map(),next=[];
      for(let i=0;i<n;i++) {
        const edge=kernel.transitions[i],key=partition[i]+":"+partition[edge[0]]+":"+partition[edge[1]];
        if(!groups.has(key))groups.set(key,groups.size);
        next.push(groups.get(key));
      }
      for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)if(next[i]!==next[j]&&words[i][j]===null) {
        let witness=null;
        for(let digit=0;digit<2;digit++) {
          const a=kernel.transitions[i][digit],b=kernel.transitions[j][digit];
          if(partition[a]!==partition[b]) {
            need(words[a][b]!==null,"missing earlier distinguishing witness");
            witness=String(digit)+words[a][b];break;
          }
        }
        need(witness!==null,"refinement split lacks a distinguishing word");
        words[i][j]=words[j][i]=witness;counters.original_distinguishing_pairs++;
      }
      rounds++;counters.refinement_rounds++;
      need(rounds<=n+2,"refinement failed to stabilize");
      if(next.every((v,i)=>v===partition[i])){partition=next;break;}
      partition=next;
    }
    const representatives=[];
    for(let i=0;i<n;i++)if(representatives[partition[i]]===undefined)representatives[partition[i]]=i;
    const order=[partition[0]],canonical=new Map([[partition[0],0]]),minimalOutputs=[],minimalEdges=[];
    for(let i=0;i<order.length;i++) {
      const rep=representatives[order[i]],edge=[];
      minimalOutputs.push(outputs[rep]);
      for(let digit=0;digit<2;digit++) {
        const target=partition[kernel.transitions[rep][digit]];
        if(!canonical.has(target)){canonical.set(target,order.length);order.push(target);}
        edge.push(canonical.get(target));
      }
      minimalEdges.push(edge);
    }
    need(order.length===representatives.length,"unreachable quotient block");
    const quotient=partition.map(block=>canonical.get(block));
    const distinguishers=[];
    for(let i=0;i<order.length;i++)for(let j=i+1;j<order.length;j++) {
      const digits=words[representatives[order[i]]][representatives[order[j]]];
      need(digits!==null,"minimal states lack a distinguishing word");
      distinguishers.push({left:i,right:j,lsb_digits:digits});
    }
    return {minimal_dfa:{root:0,outputs:minimalOutputs,transitions:minimalEdges},quotient_map:quotient,distinguishers,refinement_rounds:rounds};
  }
  for(const kernel of kernels)for(let output=0;output<outputCount;output++) {
    const code=kernel.transition_code*outputCount+output;
    const outputs=kernel.states.map(state=>outputBit(output,funcs.mappings[state[2]][0],state[4]));
    counters.output_assignments+=outputs.length;
    const result=minimize(kernel,outputs);counters.minimizations++;
    const key=JSON.stringify([result.minimal_dfa.outputs,result.minimal_dfa.transitions]);
    let classId=classByKey.get(key);
    if(classId===undefined) {
      if(counters.retained_distinguishing_pairs+result.distinguishers.length>THUE_MORSE_MEALY_LIMITS.max_distinguishing_pairs)
        incomplete("distinguishing-certificate cap reached",{unfinished_machine_code:code});
      classId=classes.length;classByKey.set(key,classId);
      classes.push({id:classId,representative_machine:code,members:[],
        minimal_dfa:result.minimal_dfa,distinguishers:result.distinguishers});
      counters.retained_distinguishing_pairs+=result.distinguishers.length;
    }
    classes[classId].members.push(code);
    machines.push({code,transition_code:kernel.transition_code,output_code:output,
      class_id:classId,quotient_map:result.quotient_map,refinement_rounds:result.refinement_rounds});
    counters.quotient_map_entries+=result.quotient_map.length;counters.machine_tables++;
  }
  const snapshot={
    schema:SCHEMA,state_count:q,start_state:0,
    input_stream:{name:"Thue-Morse",initial_symbol:0,morphism:["01","10"],index_origin:0},
    model:"complete binary letter-to-letter deterministic transducers; no initial output",
    encoding:{
      transition_code:"f0 + M*f1, where M=q^q and fa is the base-q code of delta(state,a)",
      output_code:"bit (2*state+input) is the emitted bit",
      machine_code:"transition_code * 2^(2*q) + output_code",
      function_code:"sum f(state)*q^state",
      function_composition:"compositions[f][g] encodes f after g",
      kernel_state:"[F0,F1,G0,G1,parity]; binary index digits read least significant first",
      class_order:"increasing first machine code; members in increasing machine code",
      minimal_dfa_order:"BFS from root, digit 0 before digit 1"
    },
    functions:funcs,kernels,classes,machines,
    compilation:{status:"COMPLETE",max_kernel_states:cap,counters}
  };
  const serialized=JSON.stringify(snapshot);
  if(serialized.length>THUE_MORSE_MEALY_LIMITS.max_snapshot_chars) {
    const error=new RangeError("snapshot character cap reached");error.code="SNAPSHOT_CAP";error.completed_snapshot=snapshot;throw error;
  }
  return {snapshot,summary:{
    state_count:q,transition_tables:transitionCount,output_tables_per_transition:outputCount,
    machine_tables:machines.length,infinite_output_classes:classes.length,
    kernel_states:counters.kernel_states,
    maximum_kernel_states:Math.max(...kernels.map(k=>k.states.length)),
    maximum_minimal_dfa_states:Math.max(...classes.map(c=>c.minimal_dfa.outputs.length)),
    snapshot_chars:serialized.length,counters:clone(counters)
  }};
}

/**
 * Verify the retained finite certificates and navigate without constructing
 * kernel states, minimizing output automata or expanding the input stream.
 */
function openRetainedThueMorseMealyAtlas(saved) {
  const serialized=typeof saved==="string"?saved:JSON.stringify(saved);
  need(typeof serialized==="string"&&serialized.length<=THUE_MORSE_MEALY_LIMITS.max_snapshot_chars,"invalid or oversized snapshot");
  const data=JSON.parse(serialized);
  need(data&&data.schema===SCHEMA,"unsupported atlas schema");
  const q=integer(data.state_count,1,THUE_MORSE_MEALY_LIMITS.max_states,"state_count");
  need(data.start_state===0,"start state must be zero");
  need(data.input_stream&&data.input_stream.name==="Thue-Morse"&&data.input_stream.initial_symbol===0&&data.input_stream.index_origin===0&&JSON.stringify(data.input_stream.morphism)===JSON.stringify(["01","10"]),"input-stream contract mismatch");
  const f=data.functions,M=q**q,outputCount=2**(2*q),transitionCount=M*M,total=transitionCount*outputCount;
  need(f&&f.count===M&&Array.isArray(f.mappings)&&f.mappings.length===M&&Array.isArray(f.compositions)&&f.compositions.length===M,"function table dimensions");
  const statistics={
    loaded_kernels:0,loaded_kernel_states:0,loaded_machines:0,loaded_classes:0,
    function_entry_checks:0,composition_entry_checks:0,kernel_edge_checks:0,
    kernel_reachability_visits:0,quotient_state_checks:0,quotient_edge_checks:0,
    distinguishing_words_checked:0,distinguishing_transitions:0,class_canonical_visits:0,
    class_queries:0,machine_queries:0,rank_queries:0,select_queries:0,page_queries:0,page_rows:0,
    output_queries:0,output_digit_steps:0,difference_queries:0,difference_product_states:0,
    prefix_queries:0,prefix_digit_layers:0,prefix_dp_transitions:0,
    kernel_graph_constructions:0,output_minimizations:0,input_stream_symbols_expanded:0
  };
  for(let code=0;code<M;code++) {
    need(Array.isArray(f.mappings[code])&&f.mappings[code].length===q,"function row dimension");
    let rebuilt=0,power=1;
    for(let s=0;s<q;s++){integer(f.mappings[code][s],0,q-1,"function value");rebuilt+=power*f.mappings[code][s];power*=q;statistics.function_entry_checks++;}
    need(rebuilt===code,"function code mismatch");
    need(Array.isArray(f.compositions[code])&&f.compositions[code].length===M,"composition row dimension");
  }
  integer(f.identity,0,M-1,"identity function");
  need(f.mappings[f.identity].every((v,s)=>v===s),"identity function mismatch");
  for(let a=0;a<M;a++)for(let b=0;b<M;b++) {
    let expected=0,power=1;
    for(let s=0;s<q;s++){expected+=power*f.mappings[a][f.mappings[b][s]];power*=q;}
    need(f.compositions[a][b]===expected,"composition value mismatch");statistics.composition_entry_checks++;
  }
  need(Array.isArray(data.kernels)&&data.kernels.length===transitionCount,"kernel count mismatch");
  for(let transition=0;transition<transitionCount;transition++) {
    const k=data.kernels[transition];
    need(k&&k.transition_code===transition&&k.root===0,"kernel identity mismatch");
    need(JSON.stringify(k.delta_functions)===JSON.stringify([transition%M,Math.floor(transition/M)]),"delta code mismatch");
    need(Array.isArray(k.states)&&k.states.length>=1&&k.states.length<=THUE_MORSE_MEALY_LIMITS.max_kernel_states,"kernel state dimensions");
    need(Array.isArray(k.transitions)&&k.transitions.length===k.states.length,"kernel edge dimensions");
    const keys=new Set();
    for(const state of k.states) {
      need(Array.isArray(state)&&state.length===5,"invalid kernel state");
      for(let i=0;i<4;i++)integer(state[i],0,M-1,"kernel function");
      integer(state[4],0,1,"kernel parity");
      const key=stateKey(state);need(!keys.has(key),"duplicate kernel state");keys.add(key);
    }
    need(JSON.stringify(k.states[0])===JSON.stringify([transition%M,Math.floor(transition/M),f.identity,f.identity,0]),"kernel root mismatch");
    for(let s=0;s<k.states.length;s++) {
      need(Array.isArray(k.transitions[s])&&k.transitions[s].length===2,"kernel transition row");
      for(let digit=0;digit<2;digit++) {
        const to=integer(k.transitions[s][digit],0,k.states.length-1,"kernel target");
        need(stateKey(k.states[to])===stateKey(nextKernel(k.states[s],digit,f.compositions)),"kernel recurrence mismatch");
        statistics.kernel_edge_checks++;
      }
    }
    const seen=new Set([0]),queue=[0];
    for(let i=0;i<queue.length;i++)for(const to of k.transitions[queue[i]])if(!seen.has(to)){seen.add(to);queue.push(to);}
    need(queue.length===k.states.length,"unreachable retained kernel state");
    statistics.kernel_reachability_visits+=queue.length;
    statistics.loaded_kernels++;statistics.loaded_kernel_states+=k.states.length;
  }
  need(Array.isArray(data.classes)&&data.classes.length>=1&&data.classes.length<=total,"class dimensions");
  need(Array.isArray(data.machines)&&data.machines.length===total,"machine dimensions");
  const classKeys=new Set(),expectedMembers=Array.from({length:data.classes.length},()=>[]);
  let certificatePairs=0;
  function follow(dfa,start,digits) {
    let state=start;
    for(const char of digits){state=dfa.transitions[state][char==="0"?0:1];statistics.distinguishing_transitions++;}
    return state;
  }
  for(let id=0;id<data.classes.length;id++) {
    const c=data.classes[id],d=c?.minimal_dfa;
    need(c&&c.id===id&&d&&d.root===0,"class identity mismatch");
    need(Array.isArray(d.outputs)&&d.outputs.length>=1&&d.outputs.length<=THUE_MORSE_MEALY_LIMITS.max_kernel_states,"DFA output dimensions");
    need(Array.isArray(d.transitions)&&d.transitions.length===d.outputs.length,"DFA edge dimensions");
    const n=d.outputs.length;
    for(let s=0;s<n;s++) {
      integer(d.outputs[s],0,1,"DFA output");
      need(Array.isArray(d.transitions[s])&&d.transitions[s].length===2,"DFA transition row");
      for(const to of d.transitions[s])integer(to,0,n-1,"DFA target");
    }
    const seen=new Set([0]),queue=[0];
    for(let i=0;i<queue.length;i++)for(const to of d.transitions[queue[i]])if(!seen.has(to)){seen.add(to);queue.push(to);}
    need(queue.length===n&&queue.every((v,i)=>v===i),"DFA is not in accessible canonical BFS order");
    statistics.class_canonical_visits+=n;
    need(Array.isArray(c.distinguishers)&&c.distinguishers.length===n*(n-1)/2,"incomplete minimality certificate");
    certificatePairs+=c.distinguishers.length;
    need(certificatePairs<=THUE_MORSE_MEALY_LIMITS.max_distinguishing_pairs,"distinguishing certificate cap");
    let pos=0;
    for(let a=0;a<n;a++)for(let b=a+1;b<n;b++) {
      const row=c.distinguishers[pos++];
      need(row&&row.left===a&&row.right===b&&typeof row.lsb_digits==="string"&&row.lsb_digits.length<=THUE_MORSE_MEALY_LIMITS.max_kernel_states&&/^[01]*$/.test(row.lsb_digits),"invalid distinguishing row");
      const x=follow(d,a,row.lsb_digits),y=follow(d,b,row.lsb_digits);
      need(d.outputs[x]!==d.outputs[y],"word does not distinguish minimal states");
      statistics.distinguishing_words_checked++;
    }
    const key=JSON.stringify([d.outputs,d.transitions]);need(!classKeys.has(key),"duplicate canonical output class");classKeys.add(key);
    statistics.loaded_classes++;
  }
  for(let code=0;code<total;code++) {
    const machine=data.machines[code];
    need(machine&&machine.code===code&&machine.transition_code===Math.floor(code/outputCount)&&machine.output_code===code%outputCount,"machine enumeration mismatch");
    const classId=integer(machine.class_id,0,data.classes.length-1,"machine class");
    const k=data.kernels[machine.transition_code],d=data.classes[classId].minimal_dfa,map=machine.quotient_map;
    need(Array.isArray(map)&&map.length===k.states.length,"quotient map dimensions");
    need(map[0]===0,"quotient root mismatch");
    const range=new Set();
    for(let s=0;s<k.states.length;s++) {
      const target=integer(map[s],0,d.outputs.length-1,"quotient target"),state=k.states[s];
      range.add(target);
      need(d.outputs[target]===outputBit(machine.output_code,f.mappings[state[2]][0],state[4]),"quotient output mismatch");
      statistics.quotient_state_checks++;
      for(let digit=0;digit<2;digit++) {
        need(map[k.transitions[s][digit]]===d.transitions[target][digit],"quotient edge mismatch");
        statistics.quotient_edge_checks++;
      }
    }
    need(range.size===d.outputs.length,"quotient map is not onto");
    expectedMembers[classId].push(code);statistics.loaded_machines++;
  }
  let previousRepresentative=-1;
  for(let id=0;id<data.classes.length;id++) {
    const c=data.classes[id],members=expectedMembers[id];
    need(members.length>=1&&JSON.stringify(c.members)===JSON.stringify(members),"class membership mismatch");
    need(c.representative_machine===members[0]&&members[0]>previousRepresentative,"class representative order mismatch");
    previousRepresentative=members[0];
  }
  function machineAt(code) {integer(code,0,total-1,"machine code");return data.machines[code];}
  function classAt(id) {integer(id,0,data.classes.length-1,"class id");return data.classes[id];}
  function decodeMachine(code) {
    const m=machineAt(code),k=data.kernels[m.transition_code],transitions=[],outputs=[];
    for(let s=0;s<q;s++) {
      transitions.push([f.mappings[k.delta_functions[0]][s],f.mappings[k.delta_functions[1]][s]]);
      outputs.push([outputBit(m.output_code,s,0),outputBit(m.output_code,s,1)]);
    }
    return {code,state_count:q,start_state:0,transitions,outputs,class_id:m.class_id};
  }
  function classSummary(id) {
    const c=classAt(id);return {id,representative_machine:c.representative_machine,
      machine_count:c.members.length,minimal_dfa_states:c.minimal_dfa.outputs.length,
      constant_output:c.minimal_dfa.outputs.length===1?c.minimal_dfa.outputs[0]:null};
  }
  function digitsOf(n) {return n===0n?"":n.toString(2).split("").reverse().join("");}
  function evaluate(code,index) {
    statistics.output_queries++;
    const m=machineAt(code),d=data.classes[m.class_id].minimal_dfa,n=natural(index,"index"),digits=digitsOf(n);
    let state=0;for(const bit of digits){state=d.transitions[state][bit==="0"?0:1];statistics.output_digit_steps++;}
    return {machine_code:code,class_id:m.class_id,index:n.toString(),lsb_digit_count:digits.length,terminal_state:state,output:d.outputs[state]};
  }
  function difference(leftCode,rightCode) {
    statistics.difference_queries++;
    const left=machineAt(leftCode),right=machineAt(rightCode);
    if(left.class_id===right.class_id)return {equal:true,left_machine:leftCode,right_machine:rightCode,class_id:left.class_id,certificate:"same certified canonical minimal output DFA"};
    const a=data.classes[left.class_id].minimal_dfa,b=data.classes[right.class_id].minimal_dfa;
    const nodes=[{left:0,right:0,parent:null,digit:null}],seen=new Map([["0,0",0]]);
    for(let head=0;head<nodes.length;head++) {
      const row=nodes[head];statistics.difference_product_states++;
      if(a.outputs[row.left]!==b.outputs[row.right]) {
        const path=[];let p=head;
        while(nodes[p].parent!==null){path.push(String(nodes[p].digit));p=nodes[p].parent;}
        const digits=path.reverse().join("");let index=0n,power=1n;
        for(const digit of digits){if(digit==="1")index+=power;power<<=1n;}
        return {equal:false,left_machine:leftCode,right_machine:rightCode,
          left_class:left.class_id,right_class:right.class_id,
          index:index.toString(),lsb_digits:digits,
          left_output:a.outputs[row.left],right_output:b.outputs[row.right],
          witness_order:"shortest digit word, then lexicographic LSB-digit order; not minimum numeric index",
          certificate:{nodes,expanded_nodes:head+1,first_differing_node:head}};
      }
      for(let digit=0;digit<2;digit++) {
        const x=a.transitions[row.left][digit],y=b.transitions[row.right][digit],key=x+","+y;
        if(!seen.has(key)) {
          if(nodes.length>=THUE_MORSE_MEALY_LIMITS.max_difference_states) {
            const error=new RangeError("difference query state cap reached");error.code="DIFFERENCE_CAP";
            error.partial={left_machine:leftCode,right_machine:rightCode,nodes:clone(nodes),expanded_nodes:head,current_digit:digit};throw error;
          }
          seen.set(key,nodes.length);nodes.push({left:x,right:y,parent:head,digit});
        }
      }
    }
    throw new Error("distinct certified minimal classes unexpectedly have equal roots");
  }
  function prefixOnesBelow(code,bound) {
    statistics.prefix_queries++;
    const m=machineAt(code),d=data.classes[m.class_id].minimal_dfa,N=natural(bound,"bound"),digits=digitsOf(N);
    let dp=Array.from({length:d.outputs.length},()=>[0n,0n,0n]);dp[0][1]=1n;
    let localTransitions=0;
    for(const char of digits) {
      const boundBit=char==="0"?0:1,next=Array.from({length:d.outputs.length},()=>[0n,0n,0n]);
      for(let state=0;state<dp.length;state++)for(let comparison=0;comparison<3;comparison++)if(dp[state][comparison]!==0n) {
        for(let bit=0;bit<2;bit++) {
          const cmp=bit<boundBit?0:bit>boundBit?2:comparison;
          next[d.transitions[state][bit]][cmp]+=dp[state][comparison];
          localTransitions++;statistics.prefix_dp_transitions++;
        }
      }
      dp=next;statistics.prefix_digit_layers++;
    }
    let ones=0n,zeros=0n;
    for(let state=0;state<dp.length;state++) {
      if(d.outputs[state])ones+=dp[state][0];else zeros+=dp[state][0];
    }
    need(ones+zeros===N,"prefix digit count does not cover the interval");
    return {machine_code:code,class_id:m.class_id,interval:"0 <= index < bound",
      bound:N.toString(),ones:ones.toString(),zeros:zeros.toString(),digit_layers:digits.length,
      dp_transitions:localTransitions,
      final_state_counts:dp.map((row,state)=>({state,output:d.outputs[state],less:row[0].toString(),equal:row[1].toString(),greater:row[2].toString()}))};
  }
  return Object.freeze({
    summary(){return {state_count:q,machine_tables:total,transition_tables:transitionCount,
      infinite_output_classes:data.classes.length,
      kernel_states:statistics.loaded_kernel_states,
      maximum_minimal_dfa_states:Math.max(...data.classes.map(c=>c.minimal_dfa.outputs.length)),
      interpretation:"equality of infinite output streams; not transduction-degree equivalence"};},
    classSummary(id){statistics.class_queries++;return classSummary(id);},
    classDetails(id){statistics.class_queries++;return clone(classAt(id));},
    machine(code){statistics.machine_queries++;return decodeMachine(code);},
    rankMachine(code){statistics.rank_queries++;const m=machineAt(code),c=classAt(m.class_id);return {class_id:m.class_id,rank:c.members.indexOf(code),machine_code:code};},
    selectMachine(classId,rank){statistics.select_queries++;const c=classAt(classId);integer(rank,0,c.members.length-1,"class rank");return decodeMachine(c.members[rank]);},
    classesPage(start=0,limit=100){
      integer(start,0,data.classes.length,"class page start");integer(limit,0,THUE_MORSE_MEALY_LIMITS.max_page_size,"page limit");
      statistics.page_queries++;const end=Math.min(start+limit,data.classes.length),rows=[];
      for(let i=start;i<end;i++){rows.push(classSummary(i));statistics.page_rows++;}
      return {start,total:data.classes.length,rows,next:end<data.classes.length?end:null};
    },
    machinesPage(classId,start=0,limit=100){
      const c=classAt(classId);integer(start,0,c.members.length,"machine page start");integer(limit,0,THUE_MORSE_MEALY_LIMITS.max_page_size,"page limit");
      statistics.page_queries++;const end=Math.min(start+limit,c.members.length),rows=[];
      for(let i=start;i<end;i++){rows.push({rank:i,...decodeMachine(c.members[i])});statistics.page_rows++;}
      return {class_id:classId,start,total:c.members.length,rows,next:end<c.members.length?end:null};
    },
    output:evaluate,difference,prefixOnesBelow,
    snapshot(){return clone(data);},
    statistics(){return clone(statistics);}
  });
}
module.exports={THUE_MORSE_MEALY_LIMITS,compileThueMorseMealyAtlas,openRetainedThueMorseMealyAtlas};
