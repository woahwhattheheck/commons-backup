/** Exact-source forwarding for an existing native connector host.
 * The host supplies readPage and selects its actual authenticated account.
 * No dependency, peer registration, work dispatch or notification ack is used.
 */
export function createGatewayReader({gatewayURL='http://127.0.0.1:8878',
  fetchImpl=globalThis.fetch}={}) {
  if (typeof gatewayURL!=='string' || !gatewayURL || typeof fetchImpl!=='function') {
    throw new TypeError('Existing source gateway URL and fetch implementation required');
  }
  const base=gatewayURL.replace(/\/$/,'');
  const fail=code=>{
    const error=new Error(code);
    error.name='SourceBindingError';
    error.code=code;
    throw error;
  };
  const request=async(path,body,signal)=>{
    const response=await fetchImpl(base+path,{signal,...(body===undefined?{}:
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
    if (!response.ok) fail('source_gateway_unavailable');
    return response.json();
  };
  return async({tool_name,args={},account_ref,service,signal,operation_id})=>{
    if (typeof account_ref!=='string' || !account_ref.trim()
        || typeof tool_name!=='string' || !tool_name.trim()
        || !args || typeof args!=='object' || Array.isArray(args)
        || (service!=null && (typeof service!=='string' || !service.trim()))) {
      throw new TypeError('Exact source reference, tool name and provider argument object required');
    }
    // Older gateways ignore account selectors. Inspect actual bound routes
    // before posting so they cannot run their default provider for this read.
    const inventory=await request('/v1/tools',undefined,signal);
    if (!Array.isArray(inventory?.source_bindings)) fail('source_binding_unresolved');
    const advertised=inventory.source_bindings.find(binding=>binding
      && binding.account_ref===account_ref && binding.binding_id
      && (service==null || binding.service===service));
    if (!advertised) fail('source_binding_unresolved');
    const operation=operation_id??('native-source:'+globalThis.crypto.randomUUID());
    if (typeof operation!=='string' || !operation.trim()) {
      throw new TypeError('operation_id must be a nonempty string when supplied');
    }
    const body={request_id:operation,call_id:operation,name:tool_name,
      arguments:structuredClone(args),account_ref};
    if (service!=null) body.service=service;
    const response=await request('/v1/tools/call',body,signal);
    const result=response?.result;
    if (response?.ok===false || response?.uncertain || !result || typeof result!=='object'
        || result.isError || result.error || result.uncertain) fail('source_read_unresolved');
    const bound=result.source_context;
    const evidence=bound?.binding_evidence;
    const hasEvidence=typeof evidence==='string' ? Boolean(evidence.trim())
      : evidence && typeof evidence==='object' && !Array.isArray(evidence) && Object.keys(evidence).length>0;
    if (!bound || bound.account_ref!==account_ref || !bound.binding_id || !hasEvidence
        || (service!=null && bound.service!==service) || !('result' in result)) {
      fail('source_binding_mismatch');
    }
    // Keep the complete HTTP/native envelope, including actual route evidence.
    // Existing collector traversal unwraps only its view of this retained copy.
    return {payload:response,account_ref:bound.account_ref,service:bound.service,
      binding_id:bound.binding_id,binding_evidence:structuredClone(evidence)};
  };
}

export async function collectNativePass({baseURL='http://127.0.0.1:8893', readPage,
  fetchImpl=globalThis.fetch, availableTools, concurrency=4, signal, pageSize=128}) {
  if (typeof readPage!=='function') throw new TypeError('Existing authenticated readPage binding required');
  const base=baseURL.replace(/\/$/,'');
  const request=async(path, body)=>{
    const response=await fetchImpl(base+path,{signal, ...(body===undefined?{}:
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
    const result=await response.json();
    if (!response.ok || result.ok===false) throw new Error(result.error||'telemetry_receipt_unavailable');
    return result;
  };
  const health=await request('/api/telemetry/health');
  if (health.storage?.status==='pending_storage') return {captured:0,pending_storage:true,swarm_execution_independent:true};
  const jobs=[];
  let cursor='';
  do {
    const page=await request('/api/telemetry/source-jobs?limit='+Math.max(1,pageSize)+'&cursor='+encodeURIComponent(cursor));
    jobs.push(...page.jobs);
    cursor=page.next_cursor;
  } while(cursor && !signal?.aborted);
  const available=availableTools ? new Set(availableTools) : null;
  const now=Date.now()/1000;
  const pending=[];
  let deferred=0, nextAttempt=null;
  for (const job of jobs) {
    if (!job.tool_name || job.complete || (available && !available.has(job.tool_name))) continue;
    const retryAt=[job.next_attempt_epoch,job.retry_at_epoch].reduce((latest,value)=>
      Number.isFinite(Number(value)) ? Math.max(latest,Number(value)) : latest,0);
    if (retryAt>now) {
      deferred++;
      nextAttempt=nextAttempt===null ? retryAt : Math.min(nextAttempt,retryAt);
    } else pending.push(job);
  }
  const outcomes=[];
  let next=0;
  const worker=async()=>{
    while(next<pending.length && !signal?.aborted) {
      const job=pending[next++];
      try {
        // Arguments and native results never pass through model summarization.
        const argumentsCopy=structuredClone(job.args||{});
        const observed=await readPage({tool_name:job.tool_name,args:argumentsCopy,
          account_ref:job.account_ref,service:job.service,reader:job.reader,signal});
        if (!observed || observed.account_ref!==job.account_ref || !('payload' in observed)) {
          outcomes.push({job_id:job.job_id,status:'account_binding_unresolved'});
          continue;
        }
        const receipt=await request('/api/telemetry/source-response',{
          job_id:job.job_id,reader:job.reader,arguments:argumentsCopy,tool_name:job.tool_name,
          account_ref:observed.account_ref,service:job.service,payload:observed.payload,
          binding_evidence:observed.binding_evidence});
        outcomes.push({job_id:job.job_id,status:'captured',source_record_ref:receipt.source_record_ref});
      } catch(error) {
        outcomes.push({job_id:job.job_id,status:'pending_recovery',error:error.name||'SourceReadError'});
      }
    }
  };
  await Promise.all(Array.from({length:Math.max(1,Math.min(32,concurrency,pending.length||1))},worker));
  return {captured:outcomes.filter(row=>row.status==='captured').length,
    considered:pending.length,discovered_jobs:jobs.length,outcomes,corpus_complete:false,
    deferred_jobs:deferred,next_attempt_epoch:nextAttempt,
    sampling:false,swarm_execution_independent:true};
}

export async function runNativeCollector(options) {
  const delay=Math.max(1000,options.pollMilliseconds||10000);
  while(!options.signal?.aborted) {
    try { const result=await collectNativePass(options); options.onStatus?.(result); }
    catch(error) { options.onStatus?.({status:'pending_recovery',error:error.name}); }
    if(options.signal?.aborted) break;
    await new Promise(resolve=>{
      const finish=()=>{clearTimeout(timer);options.signal?.removeEventListener('abort',finish);resolve();};
      const timer=setTimeout(finish,delay);
      options.signal?.addEventListener('abort',finish,{once:true});
    });
  }
}
