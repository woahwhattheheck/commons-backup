import { createHash } from "node:crypto";

const MIB = 1024 * 1024;
const textual = mime => mime.startsWith("text/") || /(?:json|xml|javascript)$/.test(mime);

// These are throughput bounds, not permissions. Mutations are never replayed.
export function createReadTransport({ fetchImpl = globalThis.fetch, clock = Date.now,
  maxResponseBytes = 32 * MIB, maxCacheBytes = 64 * MIB, maxEntries = 32 } = {}) {
  const cache = new Map(), pending = new Map(), cooldowns = new Map(), generations = new Map();
  let cacheBytes = 0;
  function remove(key) {
    const entry = cache.get(key);
    if (entry) cacheBytes -= entry.cost;
    cache.delete(key);
  }
  function remember(key, value, ttl, cost = value.body.length + (value.text ? Buffer.byteLength(value.text) : 0)) {
    if (cost > maxCacheBytes || ttl <= 0) return;
    remove(key);
    while (cache.size >= maxEntries || cacheBytes + cost > maxCacheBytes) remove(cache.keys().next().value);
    cache.set(key, { value, expires: clock() + ttl, cost });
    cacheBytes += cost;
  }
  function presented(value, status) {
    return { ...value, cache: { status, age_ms: Math.max(0, clock() - Date.parse(value.observed_at)) } };
  }
  async function readBody(response, limit) {
    const declared = Number(response.headers.get("content-length"));
    if (Number.isFinite(declared) && declared > limit) {
      await response.body?.cancel();
      throw new Error("response exceeded max_bytes (" + limit + ")");
    }
    if (!response.body) return Buffer.alloc(0);
    const reader = response.body.getReader(), chunks = [];
    let length = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        length += part.value.byteLength;
        if (length > limit) {
          await reader.cancel();
          throw new Error("response exceeded max_bytes (" + limit + ")");
        }
        chunks.push(Buffer.from(part.value));
      }
      return Buffer.concat(chunks, length);
    } finally { reader.releaseLock(); }
  }
  async function fetchState(url, init = {}, policy = {}) {
    const started = clock(), method = String(init.method || "GET").toUpperCase();
    const headers = new Headers(init.headers || {});
    const authenticated = headers.has("authorization") || headers.has("cookie") ||
      Boolean(new URL(url).username || new URL(url).password);
    // Hash request identity; never retain a credential value in a cache key.
    const key = createHash("sha256").update(JSON.stringify([url, method, [...headers].sort()])).digest("hex");
    const scope = new URL(url).origin + ":" + createHash("sha256")
      .update(headers.get("authorization") || headers.get("cookie") || "public").digest("hex");
    const read = method === "GET" && init.body == null;
    const limit = Math.min(maxResponseBytes, Math.max(1, Number(policy.maxBytes || maxResponseBytes)));
    const ttl = Math.max(0, Number(policy.ttlMs ?? 10000));
    const existing = cache.get(key);
    if (read && !authenticated && !policy.fresh && existing && existing.expires > clock()) {
      if (existing.value.body.length > limit) return { reached: false, ok: false,
        error: "resource exceeded max_bytes", observed_at: existing.value.observed_at,
        cache: { status: "limit", age_ms: clock() - Date.parse(existing.value.observed_at) } };
      cache.delete(key); cache.set(key, existing);
      return presented(existing.value, "hit");
    }
    // Serving an existing observation consumes no provider quota. Cooldowns
    // govern network requests, including fresh reads, not eligible cache hits.
    const retryAt = cooldowns.get(scope);
    if (retryAt && retryAt > clock()) return {
      reached: false, ok: false, status: 429, error: "provider_cooldown",
      retry_at: new Date(retryAt).toISOString(), retry_after: Math.ceil((retryAt - clock()) / 1000),
      observed_at: new Date(clock()).toISOString(), ms: 0, cache: { status: "deferred", age_ms: 0 }
    };
    if (retryAt) cooldowns.delete(scope);
    if (existing) remove(key);
    // A forced observation never joins an older ordinary observation.
    const flightKey = key + ":" + limit + ":" + Boolean(policy.fresh);
    if (read && pending.has(flightKey)) return presented(await pending.get(flightKey), "coalesced");
    const generation = generations.get(key) || { latest: 0, active: 0 };
    const ticket = ++generation.latest;
    generation.active++;
    generations.set(key, generation);
    const operation = (async () => {
      let response;
      try {
        response = await fetchImpl(url, { redirect: "follow", signal: AbortSignal.timeout(15000), ...init });
        const retry = response.headers.get("retry-after");
        if (response.status === 429 || ([403, 503].includes(response.status) && retry)) {
          const seconds = retry !== null && /^\d+(?:\.\d+)?$/.test(retry.trim()) ? Number(retry) : null;
          const until = seconds !== null ? clock() + seconds * 1000 : Date.parse(retry || "");
          const deadline = Number.isFinite(until) && until > clock() ? until : clock() + 60000;
          cooldowns.set(scope, Math.max(cooldowns.get(scope) || 0, deadline));
          // Bound provider bookkeeping without evicting an active retry deadline.
          for (const [name, value] of cooldowns) if (value <= clock()) cooldowns.delete(name);
        }
        const body = await readBody(response, limit);
        const content_type = String(response.headers.get("content-type") || "application/octet-stream").split(";", 1)[0].trim().toLowerCase();
        const value = { reached: true, ok: response.ok, status: response.status,
          ms: clock() - started, observed_at: new Date(clock()).toISOString(), body, content_type,
          ...(textual(content_type) ? { text: body.toString("utf8") } : {}),
          ...(retry ? { retry_after: retry } : {}),
          ...(cooldowns.has(scope) ? { retry_at: new Date(cooldowns.get(scope)).toISOString() } : {}) };
        // Private responses and unsuccessful reads (including raw/main 404) are not cached.
        if (read && generation.latest === ticket && !authenticated && response.ok && !response.headers.has("set-cookie") &&
            !/private|no-store/i.test(response.headers.get("cache-control") || "")) remember(key, value, ttl);
        return value;
      } catch (error) {
        return { reached: Boolean(response), ok: false, status: response?.status,
          ms: clock() - started, observed_at: new Date(clock()).toISOString(), error: String(error.message || error) };
      }
    })();
    if (read) pending.set(flightKey, operation);
    try { return presented(await operation, policy.fresh ? "fresh" : "miss"); }
    finally {
      if (read && pending.get(flightKey) === operation) pending.delete(flightKey);
      if (--generation.active === 0) generations.delete(key);
    }
  }
  return {
    fetchState,
    // Resolved public SHA metadata shares the same count/byte budget as response bodies.
    getHead(key) {
      const name = "head:" + key, entry = cache.get(name);
      if (!entry || entry.expires <= clock()) { remove(name); return undefined; }
      cache.delete(name); cache.set(name, entry);
      return entry.value;
    },
    setHead(key, value) {
      if (!/^[0-9a-f]{40}$/.test(value.value?.git_sha || "")) throw new Error("invalid public head identity");
      remember("head:" + key, value, 5000, Buffer.byteLength(JSON.stringify(value)));
    },
    stats: () => ({ entries: cache.size, bytes: cacheBytes, pending: pending.size })
  };
}

// Metadata stays responsive, reads have a finite concurrency bound, writes keep FIFO order.
export function createRpcDispatcher(handle, { isRead, isMetadata, maxReads = 4 }) {
  let writes = Promise.resolve(), activeReads = 0;
  const waiting = [];
  function drain() {
    while (activeReads < maxReads && waiting.length) {
      const item = waiting.shift(); activeReads++;
      Promise.resolve().then(() => handle(item.message)).then(item.resolve, item.reject)
        .finally(() => { activeReads--; drain(); });
    }
  }
  return function dispatch(message) {
    if (isMetadata(message)) return Promise.resolve().then(() => handle(message));
    if (isRead(message)) return new Promise((resolve, reject) => { waiting.push({ message, resolve, reject }); drain(); });
    const result = writes.then(() => handle(message));
    writes = result.catch(() => {});
    return result;
  };
}
