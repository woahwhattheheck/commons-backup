package com.local.deviceagent

import java.io.ByteArrayOutputStream
import java.io.File

/**
 * PfcFab — the ON-DEVICE White Box: the agent fabricates its OWN gate-circuits, from its own observed (input->output)
 * pairs, in pure Kotlin. Emits a TITANCIR NAND netlist (the format PfcEval runs) — a LUT-as-gates ROM (decoder + OR-tree,
 * the pfc_addr precedent). Verified byte-exact against the pairs BEFORE it is written; reversible (just a file we can delete).
 *
 * This is the FABRICATE step of the self-fabricating agent (P1): the agent grows dedicated hardware for a recurring need.
 *
 * SAFETY (§3, HARD BOUNDARY): PfcFab writes ONLY additive .pfc circuit files under filesDir/selffab/. It NEVER edits the
 * model weights, NEVER edits the app/safety code, NEVER runs host code. A fabricated circuit is pure boolean data that
 * PfcEval later evaluates (addressed gates). The self-fabricator cannot touch the alignment layer by construction.
 */
object PfcFab {

    private const val DIR = "selffab"

    /** A minimal NAND circuit builder (mirrors host titan_circuit.Circuit): wire 0=const0, 1=const1, 2..1+nIn=inputs. */
    private class Builder(val nIn: Int) {
        val ga = ArrayList<Int>(); val gb = ArrayList<Int>()
        val c0 = 0; val c1 = 1
        fun input(i: Int) = 2 + i
        fun nand(a: Int, b: Int): Int { ga.add(a); gb.add(b); return 2 + nIn + ga.size - 1 }
        fun not(a: Int) = nand(a, a)
        fun and(a: Int, b: Int) = not(nand(a, b))
        fun or(a: Int, b: Int) = nand(not(a), not(b))
        fun nWire() = 2 + nIn + ga.size
        /** 1 iff the nIn input bits equal `v` (LSB-first). */
        fun eqConst(v: Long): Int {
            var acc = c1
            for (i in 0 until nIn) acc = and(acc, if ((v shr i) and 1L == 1L) input(i) else not(input(i)))
            return acc
        }
    }

    /** Build a LUT ROM: out[j] = OR over keys k whose output has bit j set, of (input == k). Absent inputs -> 0. */
    fun buildLut(pairs: Map<Long, Long>, nIn: Int, nOut: Int): ByteArray {
        val b = Builder(nIn)
        val eqs = HashMap<Long, Int>()
        for (k in pairs.keys) eqs[k] = b.eqConst(k)
        val outs = IntArray(nOut)
        for (j in 0 until nOut) {
            var term = b.c0
            for ((k, v) in pairs) if ((v shr j) and 1L == 1L) term = b.or(term, eqs[k]!!)
            outs[j] = term
        }
        return serialize(b, nIn, outs)
    }

    private fun le32(o: ByteArrayOutputStream, v: Int) {
        o.write(v and 0xff); o.write((v shr 8) and 0xff); o.write((v shr 16) and 0xff); o.write((v shr 24) and 0xff)
    }

    /** TITANCIR: MAGIC(8) + <IIII>(nIn,nWire,nGate,nOut) + ga[] + gb[] + outs[]. */
    private fun serialize(b: Builder, nIn: Int, outs: IntArray): ByteArray {
        val o = ByteArrayOutputStream()
        o.write("TITANCIR".toByteArray(Charsets.US_ASCII))
        le32(o, nIn); le32(o, b.nWire()); le32(o, b.ga.size); le32(o, outs.size)
        for (g in b.ga) le32(o, g)
        for (g in b.gb) le32(o, g)
        for (w in outs) le32(o, w)
        return o.toByteArray()
    }

    class Fabricated(val name: String, val path: String, val gates: Int, val nIn: Int, val nOut: Int, val verified: Boolean)

    /**
     * Fabricate + VERIFY + write a LUT for observed pairs. Returns the record, or null if verification fails (never bakes
     * an unverified circuit — "a 0 is a wiring bug"). The circuit is evaluated with the SAME PfcEval that will address it.
     */
    fun fabricate(filesDir: File, name: String, pairs: Map<Long, Long>, nIn: Int, nOut: Int): Fabricated? {
        val blob = buildLut(pairs, nIn, nOut)
        val circ = PfcEval.parse(blob) ?: return null
        // byte-exact self-check: every observed key must reproduce its value under PfcEval
        for ((k, v) in pairs) {
            val got = PfcEval.toLong(PfcEval.eval(circ, PfcEval.bitsOf(k, nIn)))
            if (got != (v and ((1L shl nOut) - 1))) {
                AgentLog.log("selffab", "VERIFY FAILED for '$name' at input $k (got $got, want $v) — not baking")
                return null
            }
        }
        val dir = File(filesDir, DIR); dir.mkdirs()
        val f = File(dir, "$name.pfc"); f.writeBytes(blob)
        AgentLog.log("selffab", "fabricated '$name': ${circ.nGate} gates, ${pairs.size} pairs, byte-exact-verified, baked -> ${f.name}")
        return Fabricated(name, f.path, circ.nGate, nIn, nOut, true)
    }

    /** Address a self-fabricated circuit (single nIn-bit input -> nOut-bit output). Null if it isn't fabricated. */
    fun address(filesDir: File, name: String, input: Long): Long? {
        val circ = PfcEval.parseFile(File(File(filesDir, DIR), "$name.pfc").path) ?: return null
        return PfcEval.toLong(PfcEval.eval(circ, PfcEval.bitsOf(input, circ.nIn)))
    }

    fun list(filesDir: File): List<String> =
        File(filesDir, DIR).listFiles()?.filter { it.name.endsWith(".pfc") }?.map { it.name.removeSuffix(".pfc") } ?: emptyList()
}
