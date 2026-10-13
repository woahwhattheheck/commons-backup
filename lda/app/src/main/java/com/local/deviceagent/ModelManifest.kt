package com.local.deviceagent

import android.content.Context
import java.io.File
import java.io.RandomAccessFile

/**
 * MODEL MANIFEST DUMP — critical-path step 1 of operator->weight baking (owner: read the REAL Gemma 4 E4B tensor
 * layout ON-DEVICE and print it, so we never hardcode names/shapes/quant and never move the 4.4GB file).
 *
 * The directed-edit loop needs, for the owner's ACTUAL imported `.litertlm`: which named weight tensor (a layer's MLP
 * down/gate/up proj, attention o/q/k/v proj) maps to which file byte-range, its shape, and its int4 per-channel quant
 * (scale count + quantized dimension). SelfGrow already parses the OUTER container (header + section index); this
 * extends that to walk the embedded `tflite.Model` FlatBuffer inside EACH TFLiteModel section.
 *
 * WHAT THE OWNER'S 07-09 DUMP TAUGHT US (v1 was PARTIAL — this is v2):
 *  - The E4B `.litertlm` is a MULTI-SECTION model: ~11 type-3 (TFLITE_MODEL) sections, weights INLINE
 *    (`external-weights=false`, no type-7 blob). v1 did `firstOrNull{type==3}` and only walked the FIRST — the 167MB
 *    embedder (16 `embedder.*` tensors). The real transformer proj weights live in the OTHER type-3 sections (2.2GB,
 *    817MB, 219MB, 92MB, 44MB), which v1 never reached — and its `len>256MB` cap + heap `readFully` would have
 *    rejected/OOM'd them anyway.
 *  - v2: iterate ALL type-3 sections; read each section's tflite.Model FlatBuffer via a `RandomAccessFile` with LONG
 *    absolute positions (touches only the few KB of metadata, never the GB of weights — so the >2GB section is fine and
 *    there is no giant heap alloc and no 2GB `MappedByteBuffer` limit); fix the dtype read (TFLite `TensorType` is a
 *    BYTE enum, not int — v1's `getInt` produced the garbage `dtype=10242`); and for each interesting proj tensor,
 *    resolve its `Buffer` to a concrete (inline data byte-range OR external offset+size) so a later bake knows exactly
 *    where the int4 code + per-group scales live.
 *
 * Read-only + fully guarded — any malformed navigation just logs "partial" and moves on; it never writes the model
 * file. Output goes to AgentLog under `[selfmodel] manifest ...` for the owner to copy out of the Debug log.
 */
object ModelManifest {
    private const val MAGIC = "LITERTLM"
    private const val HEADER_END_OFF = 24
    private const val TYPE_TFLITE_MODEL = 3
    private const val TYPE_TFLITE_WEIGHTS = 7

    // Weight tensors the baking loop targets. Broadened after the 07-09 dump: LiteRT names the real decoder layer
    // weights as `…/q_einsum/…/dot_general`, `…/gating_einsum`, `…/ffw_…`, not `*_proj` — so match those op names too,
    // else the actual attention/MLP weights lose the per-section quota to the output embedder (which they did in v3).
    private val INTEREST = Regex("(down_proj|up_proj|gate_proj|o_proj|q_proj|k_proj|v_proj|proj|ffn|ffw|mlp|attn|einsum|dot_general|gating|feed_forward|linear)", RegexOption.IGNORE_CASE)

    private data class Section(val type: Int, val begin: Long, val end: Long)

    private fun leU64(b: ByteArray, off: Int): Long {
        var v = 0L; for (i in 0 until 8) v = v or ((b[off + i].toLong() and 0xFF) shl (8 * i)); return v
    }

    // --- little-endian reader over a RandomAccessFile, positions are RELATIVE to a base (the section start) ----------
    // FlatBuffer offsets are 32-bit relative jumps, but the absolute position within a >2GB section overflows Int, so
    // every position here is a Long. We only ever read a handful of small fields, so seek-per-read is fine (one-shot).
    private class Le(private val raf: RandomAccessFile, val base: Long, val limit: Long) {
        private val tmp = ByteArray(8)
        private fun read(pos: Long, n: Int): Long {
            if (pos < 0 || base + pos + n > limit) throw IndexOutOfBoundsException("pos=$pos n=$n")
            raf.seek(base + pos); raf.readFully(tmp, 0, n)
            var v = 0L; for (i in 0 until n) v = v or ((tmp[i].toLong() and 0xFF) shl (8 * i)); return v
        }
        fun i8(pos: Long): Int = read(pos, 1).toByte().toInt()          // TensorType is a signed byte enum
        fun u16(pos: Long): Int = read(pos, 2).toInt()
        fun i32(pos: Long): Int = read(pos, 4).toInt()                  // uoffset/soffset (relative)
        fun i64(pos: Long): Long = read(pos, 8)
    }

    // FlatBuffers table nav (mirrors SelfGrow's read path, promoted to Long positions for >2GB sections).
    private fun indirect(r: Le, pos: Long): Long = pos + r.i32(pos)     // follow a uoffset
    private fun field(r: Le, table: Long, idx: Int): Long {             // -> field pos, or -1 if absent
        val vtable = table - r.i32(table)                              // soffset (signed) back to the vtable
        val vtableSize = r.u16(vtable)
        val slot = 4 + idx * 2
        if (slot >= vtableSize) return -1
        val fieldOff = r.u16(vtable + slot)
        return if (fieldOff == 0) -1L else table + fieldOff
    }
    /** A vector field -> (elementsStartPos, count), or null. */
    private fun vector(r: Le, fieldPos: Long): Pair<Long, Int>? {
        if (fieldPos < 0) return null
        val vec = indirect(r, fieldPos)
        val count = r.i32(vec)
        if (count < 0 || count > 4_000_000) return null
        return (vec + 4) to count
    }
    /** Like vector(), but for a large [ubyte] WEIGHT blob (`Buffer.data`): the count is read UNSIGNED (a single
     *  inline weight buffer can exceed 2^31-1 bytes) and is NOT subject to vector()'s small structural cap (which
     *  would reject every real weight tensor and yield no byte-range — the dump's whole purpose). Returns
     *  (firstByteRelPos, byteCount). */
    private fun dataVector(r: Le, fieldPos: Long): Pair<Long, Long>? {
        if (fieldPos < 0) return null
        val vec = indirect(r, fieldPos)
        val count = r.i32(vec).toLong() and 0xFFFFFFFFL      // unsigned: weight blobs routinely exceed the 4M structural cap
        if (count <= 0L) return null
        return (vec + 4) to count
    }
    private fun string(r: Le, fieldPos: Long): String {
        if (fieldPos < 0) return ""
        return try {
            val s = indirect(r, fieldPos); val len = r.i32(s)
            if (len < 0 || len > 4096) return ""
            val a = ByteArray(len); for (i in 0 until len) a[i] = r.i8(s + 4 + i).toByte()
            String(a, Charsets.UTF_8)
        } catch (_: Exception) { "" }
    }
    private fun intVec(r: Le, fieldPos: Long, cap: Int = 16): IntArray {
        val v = vector(r, fieldPos) ?: return IntArray(0)
        val (start, count) = v
        return IntArray(minOf(count, cap)) { r.i32(start + it * 4L) }
    }

    private fun readSections(f: File): List<Section>? = try {
        RandomAccessFile(f, "r").use { raf ->
            val head = ByteArray(32); raf.seek(0); raf.readFully(head)
            if (String(head, 0, 8, Charsets.US_ASCII) != MAGIC) return null
            val headerEnd = leU64(head, HEADER_END_OFF)
            if (headerEnd <= 32 || headerEnd > f.length()) return null
            val idxLen = (headerEnd - 32).toInt()
            if (idxLen <= 8 || idxLen > 8 * 1024 * 1024) return null
            // The header index itself is small; read it into a Le over [32, headerEnd).
            val le = Le(raf, 32L, headerEnd)
            val root = indirect(le, 0)
            val smField = field(le, root, 1); if (smField < 0) return null
            val sm = indirect(le, smField)
            val v = vector(le, field(le, sm, 0)) ?: return null
            val (elems, count) = v
            if (count > 4096) return null
            (0 until count).map { i ->
                val so = indirect(le, elems + i * 4L)
                val bF = field(le, so, 1); val eF = field(le, so, 2); val dF = field(le, so, 3)
                Section(
                    if (dF >= 0) le.i8(dF) and 0xFF else 0,
                    if (bF >= 0) le.i64(bF) else 0L,
                    if (eF >= 0) le.i64(eF) else 0L)
            }
        }
    } catch (_: Exception) { null }

    /** Walk ONE tflite.Model section: log its buffers summary + interesting tensors with resolved byte-ranges.
     *  Returns (tensorsSeen, tensorsLogged). Fully guarded; on any gap logs "partial" for that section and returns.
     *  `budget[0]` is a shared, decrementing global cap on logged lines so a huge model can't blow up the paste. */
    /** CRC32 a SAMPLE of the weight bytes at [begin, begin+size) so an edit is provable (which region changed) WITHOUT
     *  hashing GBs — v4 hashed up to 64MB/region and stalled the dump ~19s on the 168MB embedder (releasing the model
     *  mid-run). Small region ⇒ hash it whole; large ⇒ hash first 128KB + last 128KB (a directed bake touches many
     *  bytes, so an end-sample reliably detects it; the exact per-target full hash is a Phase-3 concern). 's' = sampled. */
    private fun crc32Region(raf: RandomAccessFile, begin: Long, size: Long, budget: LongArray): String {
        if (size <= 0) return "-"
        return try {
            if (budget[0] <= 0) return "budget"
            val win = 128L * 1024
            val ranges = if (size <= 3 * win) listOf(begin to size)
                         else listOf(begin to win, (begin + size - win) to win)
            val crc = java.util.zip.CRC32(); val buf = ByteArray(1 shl 16); var hashed = 0L
            for ((start, len) in ranges) {
                if (budget[0] <= 0) break
                var rem = minOf(len, budget[0]); raf.seek(start)
                while (rem > 0) {
                    val n = raf.read(buf, 0, minOf(buf.size.toLong(), rem).toInt())
                    if (n <= 0) break
                    crc.update(buf, 0, n); rem -= n; budget[0] -= n; hashed += n
                }
            }
            java.lang.Long.toHexString(crc.value) + (if (hashed < size) "s" else "")
        } catch (_: Exception) { "err" }
    }

    /** Show a long tensor name as head…tail so the distinguishing part (layer index, proj type) stays visible past the
     *  long module prefix — v2 truncated at 44 chars and hid `…/layer_N/mlp/down_proj`. */
    private fun nameDisp(name: String): String =
        if (name.length <= 88) name else name.take(28) + "…" + name.takeLast(58)

    private fun walkModelSection(raf: RandomAccessFile, sec: Section, secIndex: Int, budget: IntArray, crcBudget: LongArray): Pair<Int, Int> {
        var seen = 0; var logged = 0
        try {
            val r = Le(raf, sec.begin, sec.end)
            val root = indirect(r, 0)                                   // tflite.Model root
            // Model.buffers (field 4): count + how many are external (offset>0). Keep the vector to resolve tensors.
            val bufsVec = vector(r, field(r, root, 4))
            var external = 0
            if (bufsVec != null) {
                val (bstart, bcount) = bufsVec
                val extBufs = ArrayList<Pair<Long, Long>>()            // (absolute file offset, size) of appended weight buffers
                for (i in 0 until minOf(bcount, 200000)) {
                    val bt = indirect(r, bstart + i * 4L)
                    val offF = field(r, bt, 1)                          // Buffer.offset (uint64) — >0 ⇒ external/appended
                    val off = if (offF >= 0) r.i64(offF) else 0L
                    if (off > 0L) {
                        external++
                        val szF = field(r, bt, 2); val sz = if (szF >= 0) r.i64(szF) else 0L   // Buffer.size (uint64)
                        if (sz > 0) extBufs.add((sec.begin + off) to sz)
                    }
                }
                AgentLog.log("selfmodel", "  sec#$secIndex t3 ${(sec.end - sec.begin) / 1_000_000}MB buffers=$bcount external=$external")
                // EXTERNAL-BUFFER MAP (v6): the 2.2GB of decoder weight DATA lives in these appended buffers, referenced by
                // tensors deep in 1340 subgraphs. List the LARGEST distinct external buffers directly (byte-range + CRC) so
                // a bake has the weight LOCATIONS even if the referencing tensors stay hard to reach; the size histogram
                // implies the layer dims (e.g. attention vs FFN). Scales still come from the tensor quant params (surfaced
                // by the all-subgraph walk below); this is the byte-range half of the map + a cross-check on ext@ resolution.
                if (extBufs.isNotEmpty()) {
                    val distinct = extBufs.distinctBy { it.first }.sortedByDescending { it.second }
                    AgentLog.log("selfmodel", "  sec#$secIndex ext-buffers: ${extBufs.size} appended, ${distinct.size} distinct offsets; top by size:")
                    for ((off, sz) in distinct.take(24)) {
                        val crc = crc32Region(raf, off, sz, crcBudget)
                        AgentLog.log("selfmodel", "    ext@$off+${sz}B (${sz / 1024}KB) crc=$crc")
                    }
                    // v7 SIZE HISTOGRAM (the SCALE-BUFFER map): the top-24 above are the big weight MATRICES (13.1MB FFN,
                    // 3.3MB attention); the per-channel int4 SCALE vectors (Phase-3 ScaleBake's exact edit target = DoRA
                    // magnitude) are small (KB) and sit BELOW that cutoff, so they never showed. Group ALL distinct external
                    // buffers by exact byte-size → count: one line per size bucket reveals the full decoder structure — how
                    // many FFN vs attention matrices, AND how many small scale/bias buffers and at what sizes. Confirms the
                    // scale buffers exist, their count tracks the weight-matrix count, and their per-channel granularity.
                    // Free — no CRC, just a group-by over offsets we already read. Owner runs Dump once → scale map locked.
                    val hist = distinct.groupingBy { it.second }.eachCount().entries.sortedByDescending { it.key }
                    AgentLog.log("selfmodel", "  sec#$secIndex ext-size histogram (${hist.size} distinct sizes):")
                    for (e in hist) AgentLog.log("selfmodel", "    ${e.value} × ${e.key}B (${e.key / 1024}KB)")
                }
            } else {
                AgentLog.log("selfmodel", "  sec#$secIndex t3 ${(sec.end - sec.begin) / 1_000_000}MB — no buffers table (partial)")
            }
            // Model.subgraphs (field 2) -> SubGraph.tensors (field 0) -> Tensor{shape0,type1(byte),buffer2,name3,quant4}.
            val sgs = vector(r, field(r, root, 2)) ?: run {
                AgentLog.log("selfmodel", "  sec#$secIndex — no subgraphs (partial)"); return seen to logged
            }
            val (sgStart, sgCount) = sgs
            // v3 PER-SECTION budget (owner's 07-09 dump: a Conformer AUDIO encoder ate the single global budget, so the
            // main Gemma decoder — the sections after it — never logged). PRIORITIZE int4 weight tensors (dt=19 = the
            // bake targets), keep a few other stored weights, and 2 activation tensors just to show the naming; skip the
            // rest of the activation/empty-buffer noise. So EVERY section — including sec#10, the 2.26GB decoder — logs.
            // v5: the decoder LAYER weights never surfaced (v4 dump: sec#10 logged only the output embedder + KV/norms).
            // Two causes: (a) the subgraph cap (was 8) skipped the decoder's per-layer subgraphs, and (b) name-matching
            // is unreliable (LiteRT names weights `…/einsum/dot_general`, and the decoder's may differ again). Fix both:
            // walk ALL subgraphs (cap 512) and prioritize by STRUCTURE — any int4 (dt=19) weight tensor that is NOT the
            // vocab embedder (scaleN≈262144). Also count int4 tensors SEEN (not just logged) so the dump tells us whether
            // the walk even reaches the decoder weights vs. they live somewhere this walk doesn't go.
            var projLogged = 0; var int4Logged = 0; var otherLogged = 0; var sampleLogged = 0; var int4Seen = 0
            // v6: the v5 diagnostic showed sec#10 = 1340 subgraphs with the 512 cap finding only 2 int4 tensors — the
            // decoder layer weights are in the DEEP subgraphs. Walk ALL of them (cap 4096) so those tensors surface.
            for (s in 0 until minOf(sgCount, 4096)) {
                val sg = indirect(r, sgStart + s * 4L)
                val tv = vector(r, field(r, sg, 0)) ?: continue
                val (tStart, tCount) = tv
                seen += tCount
                for (i in 0 until tCount) {
                    if (budget[0] <= 0) return seen to logged            // global backstop cap
                    val t = indirect(r, tStart + i * 4L)
                    val name = string(r, field(r, t, 3))
                    val shape = intVec(r, field(r, t, 0)).joinToString(",")
                    val dtypeF = field(r, t, 1); val dtype = if (dtypeF >= 0) r.i8(dtypeF) else -1   // BYTE enum (19=int4)
                    val bufF = field(r, t, 2); val bufIdx = if (bufF >= 0) r.i32(bufF) else -1
                    // Quantization (field 4) -> scale (field 2, float32 vec) count + quantized_dimension. The `details`
                    // UNION occupies TWO vtable slots (details_type=4, details=5), so quantized_dimension is field 6 (not 5).
                    var scaleN = 0; var qdim = -1
                    val qF = field(r, t, 4)
                    if (qF >= 0) {
                        val q = indirect(r, qF)
                        vector(r, field(r, q, 2))?.let { scaleN = it.second }
                        val qdF = field(r, q, 6); if (qdF >= 0) qdim = r.i32(qdF)
                    }
                    // Resolve the buffer this tensor points at -> concrete file location (inline data range OR offset).
                    var loc = "buf=$bufIdx?"
                    var dataBegin = -1L; var dataSize = 0L        // absolute weight-byte range, for the provability CRC
                    if (bufsVec != null && bufIdx in 0 until bufsVec.second) {
                        val bt = indirect(r, bufsVec.first + bufIdx * 4L)
                        val offF = field(r, bt, 1); val off = if (offF >= 0) r.i64(offF) else 0L
                        if (off > 0L) {
                            val szF = field(r, bt, 2); val sz = if (szF >= 0) r.i64(szF) else 0L
                            // Appended weights (sec#10 has 791). Buffer.offset base is ambiguous (canonical = file-relative;
                            // but a tflite serialized standalone then concatenated → section-relative). Assume section-relative,
                            // print the raw offset, AND flag OOB>secEnd — if the assumed base ran the range past the section's
                            // own end, the base is wrong (Phase 3 must NOT write there). Confirms the offset base on the dump.
                            dataBegin = sec.begin + off; dataSize = sz
                            val oob = if (dataBegin + sz > sec.end) " OOB>secEnd" else ""
                            loc = "ext@$dataBegin+${sz}B(rawoff=$off$oob)"
                        } else {
                            val dv = dataVector(r, field(r, bt, 0)) // inline Buffer.data [ubyte] vector (unsigned, uncapped)
                            if (dv != null) { dataBegin = sec.begin + dv.first; dataSize = dv.second; loc = "inline@$dataBegin+${dv.second}B" }
                            else loc = "buf=$bufIdx empty"
                        }
                    }
                    val hasWeights = dataBegin >= 0 && dataSize > 0
                    val nameMatch = name.isNotEmpty() && INTEREST.containsMatchIn(name)
                    if (dtype == 19 && hasWeights) int4Seen++
                    // The vocab embedder / unembedding is int4 too but huge (scaleN = vocab 262144); exclude it from the
                    // priority bucket so it can't starve the decoder LAYER weights (which is what happened in v3/v4).
                    val isVocab = scaleN >= 200_000 || shape.startsWith("262144")
                    // STRUCTURE-based priority: any non-vocab int4 weight matrix is a bake target — surface it regardless
                    // of name (name-matching kept missing the decoder weights). Then the vocab embedder, a few other
                    // stored weights, then 2 activation samples. Everything else (activation noise) is skipped.
                    val doLog = when {
                        dtype == 19 && hasWeights && !isVocab && projLogged < 40 -> { projLogged++; true }
                        dtype == 19 && hasWeights && int4Logged < 3 -> { int4Logged++; true }
                        hasWeights && dtype != 19 && otherLogged < 3 -> { otherLogged++; true }
                        !hasWeights && sampleLogged < 2 -> { sampleLogged++; true }
                        else -> false
                    }
                    if (!doLog) continue
                    // '*' flags a likely proj/attn/mlp tensor by name; head…tail keeps the layer/proj visible past the
                    // long module prefix (v2 truncated at 44 chars and hid it). CRC32 the weight bytes for provability.
                    val hint = if (nameMatch) "*" else ""
                    val crc = if (hasWeights) crc32Region(raf, dataBegin, dataSize, crcBudget) else "-"
                    AgentLog.log("selfmodel", "  T$hint ${nameDisp(name)} shape=[$shape] dt=$dtype scaleN=$scaleN qdim=$qdim $loc crc=$crc")
                    logged++; budget[0]--
                }
            }
            // DIAGNOSTIC (v5): subgraph count + how many int4 weight tensors this walk actually SAW. If a big section
            // shows int4seen≈0 despite GBs of weights, the weights live where this subgraph/tensor walk doesn't reach
            // (a signpost to fix the localizer, not a dead end).
            AgentLog.log("selfmodel", "  sec#$secIndex done: subgraphs=$sgCount int4seen=$int4Seen tensorsSeen=$seen logged=$logged")
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "  sec#$secIndex walk failed (${e.message}) — partial")
        }
        return seen to logged
    }

    /** Dump the active model's structure to `[selfmodel] manifest` in the Debug log. Off-thread (reads slices of the
     *  GB file). Best-effort: logs whatever it parsed, tagged partial on any gap, never writes. Returns a short status. */
    fun dump(ctx: Context): String {
        val settings = SettingsManager(ctx)
        val f = settings.getModelPath()?.let { File(it) }
        if (f == null || !f.exists()) { AgentLog.log("selfmodel", "manifest: no model imported"); return "No model imported." }
        val secs = readSections(f)
        if (secs.isNullOrEmpty()) { AgentLog.log("selfmodel", "manifest: container did not parse (not a .litertlm?)"); return "Container did not parse." }
        val layout = secs.joinToString(" ") { "t${it.type}:${(it.end - it.begin) / 1024}KB" }
        val hasExternalSection = secs.any { it.type == TYPE_TFLITE_WEIGHTS }
        AgentLog.log("selfmodel", "manifest v2 size=${f.length() / 1_000_000}MB sections=[$layout] weights-section=$hasExternalSection")
        val models = secs.filter { it.type == TYPE_TFLITE_MODEL }
        if (models.isEmpty()) { AgentLog.log("selfmodel", "manifest: no TFLiteModel section — partial"); return "No graph section." }
        return try {
            RandomAccessFile(f, "r").use { raf ->
                var totalSeen = 0; var totalLogged = 0
                val budget = intArrayOf(500)                            // global backstop; per-section quotas do the real capping now
                val crcBudget = longArrayOf(512L * 1024 * 1024)         // shared cap on bytes CRC'd (keeps a manual dump fast)
                secs.forEachIndexed { idx, sec ->
                    if (sec.type != TYPE_TFLITE_MODEL) return@forEachIndexed
                    val (seen, logged) = walkModelSection(raf, sec, idx, budget, crcBudget)
                    totalSeen += seen; totalLogged += logged
                }
                AgentLog.log("selfmodel", "manifest done: modelSections=${models.size} tensors=$totalSeen logged=$totalLogged — copy the [selfmodel] lines")
                "Dumped: $totalSeen tensors across ${models.size} model section(s). See the Debug log ([selfmodel] lines)."
            }
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "manifest: walk failed (${e.message}) — partial (section layout above is still valid)")
            "Partial dump — section layout logged; walk hit ${e.message}."
        }
    }

    /** Lean list of a section's EXTERNAL (appended) weight buffers as (absoluteOffset, size) — the same map
     *  `walkModelSection` logs, without the per-tensor walk. The divergence diff uses it to NAME which weight a
     *  changed byte fell in. Guarded; empty on any parse gap. */
    private fun extBuffers(raf: RandomAccessFile, sec: Section): List<Pair<Long, Long>> = try {
        val r = Le(raf, sec.begin, sec.end)
        val root = indirect(r, 0)
        val bufsVec = vector(r, field(r, root, 4))
        if (bufsVec == null) emptyList() else {
            val (bstart, bcount) = bufsVec
            val out = ArrayList<Pair<Long, Long>>()
            for (i in 0 until minOf(bcount, 200_000)) {
                val bt = indirect(r, bstart + i * 4L)
                val offF = field(r, bt, 1); val off = if (offF >= 0) r.i64(offF) else 0L
                if (off > 0L) {
                    val szF = field(r, bt, 2); val sz = if (szF >= 0) r.i64(szF) else 0L
                    if (sz > 0) out.add((sec.begin + off) to sz)
                }
            }
            out
        }
    } catch (_: Exception) { emptyList() }

    /** PHASE 3 target set: the DECODER's per-channel FP32 SCALE / RMSNorm / bias vectors — the small external buffers
     *  (the 10240 B = 2560-float, 2048 B, 1024 B, 512 B buckets from the v7 histogram). These are the smooth, bounded
     *  DoRA-magnitude knobs `ScaleBake` nudges (never the raw int4 code). Returns (absoluteOffset, sizeBytes), byte-range
     *  ready. Read-only; empty on any parse gap. */
    fun scaleBuffers(ctx: Context): List<Pair<Long, Long>> {
        val settings = SettingsManager(ctx)
        val f = settings.getModelPath()?.let { File(it) } ?: return emptyList()
        if (!f.exists()) return emptyList()
        val secs = readSections(f) ?: return emptyList()
        val decoder = secs.filter { it.type == TYPE_TFLITE_MODEL }.maxByOrNull { it.end - it.begin } ?: return emptyList()
        return try {
            RandomAccessFile(f, "r").use { raf ->
                extBuffers(raf, decoder).filter { it.second in 512L..12_288L && it.second % 4L == 0L }
                    .distinctBy { it.first }.sortedBy { it.first }
            }
        } catch (_: Exception) { emptyList() }
    }

    /** DS4 SENSITIVITY RETARGET (07-11 — the DwarfStar4 finding): the decoder's REDUNDANT BULK — the int4 FFN weight
     *  matrices (`[2560,10240]` int4 = **13,107,200 B** each, 126 of them per §2.1). DS4's asymmetric-quant map ranks
     *  this class as SAFE to edit HARD (the experts/FFN are individually redundant), while the scale/norm vectors
     *  `scaleBuffers` returns are the MOST-protected class (norms=F32, never touch). So a DIRECTED weight bake edits
     *  int4 nibbles HERE — a real, tolerant lever with a wide window — instead of the delicate scales (gentle nudge
     *  no-ops, hard nudge breaks: no useful window). Attention/embeddings are deliberately EXCLUDED (DS4 protects
     *  them). Returns (absoluteOffset, sizeBytes). Read-only; empty on any parse gap. */
    fun ffnWeightBuffers(ctx: Context): List<Pair<Long, Long>> {
        val settings = SettingsManager(ctx)
        val f = settings.getModelPath()?.let { File(it) } ?: return emptyList()
        if (!f.exists()) return emptyList()
        val secs = readSections(f) ?: return emptyList()
        val decoder = secs.filter { it.type == TYPE_TFLITE_MODEL }.maxByOrNull { it.end - it.begin } ?: return emptyList()
        return try {
            RandomAccessFile(f, "r").use { raf ->
                extBuffers(raf, decoder).filter { it.second == 13_107_200L }   // the [2560,10240] int4 FFN class only
                    .distinctBy { it.first }.sortedBy { it.first }
            }
        } catch (_: Exception) { emptyList() }
    }

    /** Name a changed byte's home buffer by its size (from the 07-09 histogram; see docs/E4B_ARCHITECTURE §2.1). */
    private fun sizeClass(sz: Long): String = when (sz) {
        13_107_200L -> "FFN[2560,10240]"
        27_525_120L -> "fused/large-proj"
        5_242_880L, 2_621_440L, 1_310_720L, 655_360L -> "attention-proj"
        167_772_160L -> "embedder(tied)"
        10_240L, 2_048L, 1_024L, 512L -> "scale/norm/bias"
        else -> "${sz}B-buf"
    }

    /** DIVERGENCE DUMP — quantify how far the owner's LIVE model has drifted from the pristine stock BASELINE: the
     *  evidence that our OWN self_evolve/self_grow rewrote the weights on-device (the whole endeavor; docs/E4B §5A).
     *  Reports: file-size delta (self_grow additions), per-section size diff (WHERE growth landed), the WeightGenome
     *  journal window, and — when the two files are still byte-aligned (no grow) — an EXACT byte-compare that locates
     *  the self_evolve edits and names which weight buffer each changed byte fell in. A SAMPLED CRC would miss a
     *  sparse mid-buffer nibble flip, so this reads every byte of both files. Read-only on BOTH files; off-thread. */
    fun divergence(ctx: Context): String {
        val settings = SettingsManager(ctx)
        val active = settings.getModelPath()?.let { File(it) }
        if (active == null || !active.exists()) { AgentLog.log("selfmodel", "divergence: no model imported"); return "No model imported." }
        val beats = WeightGenome.beatCount(ctx)
        val baseline = ModelStore.baselineFile(ctx)
        if (baseline == null || !baseline.exists()) {
            AgentLog.log("selfmodel", "divergence: NO pristine baseline stashed — can't diff. Ground-truth stock = a fresh Hugging Face re-import. genome window holds $beats recent beat(s).")
            return "No baseline to diff against (see [selfmodel])."
        }
        val da = active.length(); val db = baseline.length(); val delta = da - db
        AgentLog.log("selfmodel", "divergence: active=${da}B baseline=${db}B delta=${delta}B (delta>0 ⇒ self_grow added params). genome window=$beats beat(s).")
        // Section-layout diff — localizes self_grow (which section widened).
        try {
            val sa = readSections(active); val sb = readSections(baseline)
            if (sa != null && sb != null) {
                if (sa.size != sb.size) AgentLog.log("selfmodel", "  section COUNT differs: active=${sa.size} baseline=${sb.size} (structure changed)")
                for (i in 0 until minOf(sa.size, sb.size)) {
                    val za = sa[i].end - sa[i].begin; val zb = sb[i].end - sb[i].begin
                    if (za != zb) AgentLog.log("selfmodel", "  sec#$i size changed: active=${za}B baseline=${zb}B (Δ${za - zb}B)")
                }
            }
        } catch (_: Exception) {}
        if (delta != 0L) {
            AgentLog.log("selfmodel", "  sizes differ ⇒ self_grow shifted the layout; an exact byte-diff needs role-alignment (deferred). Size + section deltas above localize the growth. NOTE: baseline is only truly STOCK if stashed at import before any edit.")
            return "Divergence dumped (grown model) — see [selfmodel]."
        }
        // Byte-aligned (no grow) ⇒ EXACT compare finds the self_evolve edits.
        return try {
            val decoder = readSections(active)?.filter { it.type == TYPE_TFLITE_MODEL }?.maxByOrNull { it.end - it.begin }
            val ext = (if (decoder != null) RandomAccessFile(active, "r").use { extBuffers(it, decoder) } else emptyList()).sortedBy { it.first }
            val ch = 1 shl 20
            val ba = ByteArray(ch); val bb = ByteArray(ch)
            var diffBytes = 0L; var pos = 0L; var mapped = 0
            val classHits = HashMap<String, Long>()
            RandomAccessFile(active, "r").use { ra -> RandomAccessFile(baseline, "r").use { rb ->
                while (pos < da) {
                    val want = minOf(ch.toLong(), da - pos).toInt()
                    ra.seek(pos); ra.readFully(ba, 0, want)
                    rb.seek(pos); rb.readFully(bb, 0, want)
                    for (k in 0 until want) if (ba[k] != bb[k]) {
                        diffBytes++
                        if (mapped < 50_000) {                       // map a bounded sample to buffers; the COUNT is unbounded
                            val at = pos + k
                            val cls = ext.firstOrNull { at >= it.first && at < it.first + it.second }?.let { sizeClass(it.second) } ?: "non-decoder"
                            classHits[cls] = (classHits[cls] ?: 0L) + 1L; mapped++
                        }
                    }
                    pos += want
                }
            }}
            val pct = if (da > 0) diffBytes.toDouble() * 100.0 / da else 0.0
            AgentLog.log("selfmodel", "  byte-diff: $diffBytes of ${da} bytes differ (${"%.5f".format(pct)}%) = self_evolve edits vs baseline")
            if (classHits.isEmpty()) AgentLog.log("selfmodel", "  (no differing bytes — active is byte-identical to the baseline)")
            else classHits.entries.sortedByDescending { it.value }.forEach { AgentLog.log("selfmodel", "    ${it.value} changed byte(s) in ${it.key}") }
            AgentLog.log("selfmodel", "  divergence done. NOTE: baseline is only truly STOCK if stashed at import before any edit; else this is drift-since-baseline.")
            "Divergence dumped — $diffBytes bytes differ. See [selfmodel]."
        } catch (e: Exception) {
            AgentLog.log("selfmodel", "divergence byte-diff failed (${e.message}) — size/section deltas above are still valid")
            "Partial divergence — see [selfmodel]."
        }
    }
}
