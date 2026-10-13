package com.local.deviceagent

import android.content.Context
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * SELF-GROW (INV-60 — targeted expansion; owner: "add to its own file and increase it… start from a smaller model
 * and build up to a bigger one. It could add params much easier and faster than other methods because it doesn't
 * require training or millions in compute"). The sibling of `SelfEvolve`: instead of nudging EXISTING int4 weights,
 * the agent ADDS parameters to its OWN `.litertlm` model file, so total capacity grows — a cheap STRUCTURAL file
 * operation (no gradient training, no compute cluster), and the proven operator/σ/self-evolve layer FILLS the new
 * capacity over time.
 *
 * THE MECHANISM (grounded in the runtime — LiteRT-LM reads every tensor dim from the embedded TFLite FlatBuffer at
 * load and only checks `major_version == 1`, so a SELF-CONSISTENT grown model loads on the unmodified load path):
 * the minimal function-preserving grow is to WIDEN ONE MLP block — its up/gate projections gain output rows and its
 * down projection gains matching input COLUMNS, with the new down columns = ZERO so the block's output is unchanged
 * at insertion (the added capacity is DORMANT until the operator/self-evolve layer moves it off zero). The block's
 * internal hidden dim is exposed at no signature boundary, so nothing else in the graph changes. int4 packs two
 * codes/byte, so an added axis stays byte-aligned and each new column-group gets its own per-group scale.
 *
 * `.litertlm` layout (Agent-verified against the LiteRT-LM source): a fixed header — magic `"LITERTLM"` at [0,8),
 * `major`/`minor`/`patch` uint32-LE, then `header_end_offset` (uint64-LE) at byte 24 — followed by the index
 * FlatBuffer at [32, header_end_offset) and 16 KB-aligned section payloads (the `TFLiteModel` graph FlatBuffer, an
 * optional external `TFLiteWeights` blob, tokenizer, metadata). A grow edits the TFLite section's shapes/quant + the
 * weight bytes and repacks with corrected section offsets; the memory-safe path APPENDS int4 bytes to an external
 * `TFLiteWeights` section so the multi-GB bulk is never re-serialized.
 *
 * STAGE: this is A1 — the safe container-parse scaffold + the structural sanity check used by the junk-bloat guard.
 * `growActiveFile` PARSES and validates the container and returns false (no bytes written) so the model file is
 * untouched while the beat/guard/snapshot plumbing is exercised; the function-preserving MLP widen + repack is A2.
 *
 * SAFETY (owner's ceiling = "no ceiling except critical failure where it bloats with junk"): the recovery net is a
 * rolling snapshot ring + a BRICK-GUARD (auto-restore if a grown file won't load) + the [structuralSanityOk] check
 * below (reject a malformed / runaway/junk-bloat write BEFORE it is kept) + a post-grow generate-probe in the caller
 * (revert if the reloaded model emits degenerate output). Gated behind `self_grow`; on-device only; UNTESTED in CI
 * (it operates on the real multi-GB model file). The engine MUST be closed before an edit (a loaded file is mmap'd).
 */
object SelfGrow {
    private const val MAGIC = "LITERTLM"
    private const val HEADER_END_OFF = 24               // byte offset of the uint64-LE header_end_offset
    // A single function-preserving MLP widen adds a bounded number of int4 columns; a grown file that balloons far
    // past this is JUNK-BLOAT, not a grow — the sanity check rejects it (owner's "critical failure where it bloats").
    const val MAX_GROW_DELTA_BYTES = 64L * 1024 * 1024  // one widen beat may add at most ~64 MB of new weight bytes

    // AnySectionDataType (schema/core/litertlm_header_schema.fbs): the section table's type tags.
    private const val TYPE_TFLITE_MODEL = 3     // the embedded tflite.Model FlatBuffer (holds tensor SHAPES)
    private const val TYPE_TFLITE_WEIGHTS = 7   // external weight blob referenced by the model (the memory-safe grow path)

    /** Parsed `.litertlm` header. */
    private data class Header(val major: Long, val headerEnd: Long)

    /** One section of the container: its type tag + byte range in the file. */
    private data class Section(val type: Int, val begin: Long, val end: Long)

    private fun leU32(b: ByteArray, off: Int): Long =
        (b[off].toLong() and 0xFF) or
        ((b[off + 1].toLong() and 0xFF) shl 8) or
        ((b[off + 2].toLong() and 0xFF) shl 16) or
        ((b[off + 3].toLong() and 0xFF) shl 24)

    private fun leU64(b: ByteArray, off: Int): Long {
        var v = 0L
        for (i in 0 until 8) v = v or ((b[off + i].toLong() and 0xFF) shl (8 * i))
        return v
    }

    /** Read + validate the fixed `.litertlm` header (magic + version + header_end pointer). Null if it isn't a
     *  parseable container — the guard treats that as "do not touch it". Read-only (opens "r"). */
    private fun readHeader(f: File): Header? {
        if (!f.exists() || f.length() < 64) return null
        return try {
            RandomAccessFile(f, "r").use { raf ->
                val head = ByteArray(32)
                raf.seek(0); raf.readFully(head)
                if (String(head, 0, 8, Charsets.US_ASCII) != MAGIC) return null
                val major = leU32(head, 8)
                val headerEnd = leU64(head, HEADER_END_OFF)
                if (headerEnd < 32 || headerEnd > f.length()) return null
                Header(major, headerEnd)
            }
        } catch (_: Exception) { null }
    }

    /** JUNK-BLOAT GUARD (owner's only ceiling). After a grow, before the grown file is trusted, confirm it is still a
     *  structurally-valid `.litertlm` (header intact, `major == 1`, header_end pointer in range) AND that it grew by a
     *  SANE, BOUNDED amount — added bytes in (0, MAX_GROW_DELTA_BYTES]. A negative or runaway delta = junk-bloat →
     *  reject (the caller reverts to the last snapshot). */
    fun structuralSanityOk(f: File, preSizeBytes: Long): Boolean {
        val h = readHeader(f) ?: return false
        if (h.major != 1L) return false
        val delta = f.length() - preSizeBytes
        return delta in 1L..MAX_GROW_DELTA_BYTES
    }

    /** Apply ONE function-preserving parameter-adding grow to the ACTIVE model file IN PLACE, seeded by the agent's
     *  recent activity ([seed] from the log tail, like SelfEvolve). The caller MUST have closed the engine first and
     *  MUST reload afterward; a corrupt/junk result is caught by [structuralSanityOk] + the brick-guard. Returns true
     *  only if bytes were actually written (so the caller runs the post-grow probe/guard only on a real grow).
     *
     *  A1: parse + validate the container and return false (no write) — the function-preserving MLP-block widen +
     *  repack lands in A2. This keeps the model file untouched while the beat/guard/snapshot plumbing runs live. */
    fun growActiveFile(ctx: Context, settings: SettingsManager, seed: Long): Boolean {
        val f = settings.getModelPath()?.let { File(it) } ?: return false
        val h = readHeader(f)
        if (h == null) {
            AgentLog.log("selfgrow", "active model is not a parseable .litertlm — skip grow")
            return false
        }
        // A2a: read the container index to enumerate sections + detect the layout. The growable region is the
        // TFLite model + its weights; the MEMORY-SAFE grow appends new int4 bytes to an EXTERNAL TFLiteWeights
        // section (the multi-GB bulk is never re-serialized). A single-file model (weights inside the graph
        // FlatBuffer) is skipped for now — an in-memory GB re-serialize would OOM (§8); its streaming widen is A2b+.
        val sections = readIndexSections(f)
        if (sections == null || sections.isEmpty()) {
            AgentLog.log("selfgrow", "container OK (v${h.major}, ${f.length() / 1_000_000}MB) but the section index " +
                "didn't parse — skip grow (safe: nothing written)")
            return false
        }
        val model = sections.firstOrNull { it.type == TYPE_TFLITE_MODEL }
        val weights = sections.firstOrNull { it.type == TYPE_TFLITE_WEIGHTS }
        val map = sections.joinToString(" ") { "t${it.type}:${(it.end - it.begin) / 1024}KB" }
        AgentLog.log("selfgrow", "layout [$map] model=${model != null} extWeights=${weights != null} " +
            "size=${f.length() / 1_000_000}MB seed=${seed.toString(16)}")
        if (model == null) {
            AgentLog.log("selfgrow", "no TFLiteModel section — skip grow")
            return false
        }
        if (weights == null) {
            AgentLog.log("selfgrow", "single-file model (weights in the graph FlatBuffer) — streaming widen deferred, skip")
            return false
        }
        // A2b: parse the TFLite Model graph FlatBuffer (small — shapes/quant only, weights are external), widen one
        // MLP block's up/gate rows + down columns (new down columns ZERO ⇒ output unchanged), extend each new int4
        // column-group's scale, append the new packed-int4 bytes to the TFLiteWeights section [${weights.begin}), and
        // repack with corrected section offsets — then return true so the junk-bloat guard + probe validate or revert.
        AgentLog.log("selfgrow", "external-weights layout — growable region located; function-preserving MLP widen lands next")
        return false
    }

    // --- minimal FlatBuffers table reader (pure ByteBuffer, no library API on the read path so it can't break on a
    // version mismatch; guarded — any malformed navigation returns null and the grow is a safe no-op) -------------

    /** Absolute buffer position of table field #[fieldIndex] (vtable slot 4 + 2*index), or -1 if the field is absent. */
    private fun fbField(buf: ByteBuffer, tablePos: Int, fieldIndex: Int): Int {
        val vtable = tablePos - buf.getInt(tablePos)               // SOFFSET back to the vtable
        val vtableSize = buf.getShort(vtable).toInt() and 0xFFFF
        val slot = 4 + fieldIndex * 2
        if (slot >= vtableSize) return -1
        val fieldOff = buf.getShort(vtable + slot).toInt() and 0xFFFF
        return if (fieldOff == 0) -1 else tablePos + fieldOff
    }

    /** Follow a uoffset at [pos] to the sub-table / vector it points to. */
    private fun fbIndirect(buf: ByteBuffer, pos: Int): Int = pos + buf.getInt(pos)

    /** Parse the `.litertlm` index FlatBuffer (`LiteRTLMMetaData` → `SectionMetadata.objects` → `SectionObject`) into
     *  the list of sections (type + byte range). Null on any parse issue (⇒ the caller safely skips the grow). */
    private fun readIndexSections(f: File): List<Section>? {
        return try {
            RandomAccessFile(f, "r").use { raf ->
                val head = ByteArray(32); raf.seek(0); raf.readFully(head)
                if (String(head, 0, 8, Charsets.US_ASCII) != MAGIC) return null
                val headerEnd = leU64(head, HEADER_END_OFF)
                if (headerEnd <= 32 || headerEnd > f.length()) return null
                val idxLen = (headerEnd - 32).toInt()
                if (idxLen <= 8 || idxLen > 8 * 1024 * 1024) return null       // the index is small
                val idx = ByteArray(idxLen); raf.seek(32); raf.readFully(idx)
                val buf = ByteBuffer.wrap(idx).order(ByteOrder.LITTLE_ENDIAN)   // FlatBuffers are little-endian
                val root = fbIndirect(buf, 0)                                   // root uoffset at the buffer start
                val smField = fbField(buf, root, 1); if (smField < 0) return null      // LiteRTLMMetaData.section_metadata
                val sm = fbIndirect(buf, smField)
                val objField = fbField(buf, sm, 0); if (objField < 0) return null       // SectionMetadata.objects (vector)
                val vecStart = fbIndirect(buf, objField)
                val count = buf.getInt(vecStart)
                if (count < 0 || count > 4096) return null
                val elems = vecStart + 4
                val out = ArrayList<Section>(count)
                for (i in 0 until count) {
                    val so = fbIndirect(buf, elems + i * 4)                     // vector of offsets → SectionObject tables
                    val bF = fbField(buf, so, 1); val eF = fbField(buf, so, 2); val dF = fbField(buf, so, 3)
                    val begin = if (bF >= 0) buf.getLong(bF) else 0L
                    val end = if (eF >= 0) buf.getLong(eF) else 0L
                    val dtype = if (dF >= 0) buf.get(dF).toInt() and 0xFF else 0
                    out.add(Section(dtype, begin, end))
                }
                out
            }
        } catch (_: Exception) { null }
    }
}
