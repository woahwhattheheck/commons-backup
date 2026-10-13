package com.local.deviceagent

import java.io.File

/**
 * PfcEval — the on-device pfc runtime: evaluate a fabricated gate-circuit (the White Box's output) BYTE-EXACT, on the
 * phone, in pure Kotlin. This is the substrate the fabricated SANDBOX (pfc_cpu32/pfc_ram) and the self-fabricating agent
 * address: a circuit's bytes ARE the machine; addressing its outputs computes it.
 *
 * SAFETY (§3): this is NOT host code execution / a terminal. It reads a STORED gate netlist and ripples it — addressed
 * stored gates, no host process, no code channel. It only computes a pure boolean function (inputs -> outputs); it never
 * touches the accessibility executor, weights, or the network. It is the safe, contained compute capability.
 *
 * Formats (decoded from titan.gguf, see memory pfc-binary-formats-decoded):
 *  - TITANCIR : MAGIC(8) + <IIII>(n_in,n_wire,n_gate,n_out) + ga[n_gate] i32 + gb[n_gate] i32 + outs[n_out] i32. All NAND.
 *  - PFCTYPED : MAGIC(8) + <IIII> + n_gate*(op u8 + a i32 + b i32) + outs[n_out] i32. op 0=NAND 1=AND 2=OR 3=XOR 4=NOT.
 * Wire convention (both): 0=const0, 1=const1, 2..1+n_in = inputs, then one wire per gate in topological order.
 */
object PfcEval {

    class Circuit(
        val nIn: Int, val nWire: Int, val nGate: Int, val nOut: Int,
        val typed: Boolean,
        val op: IntArray,          // typed only (else empty); 0..4
        val ga: IntArray, val gb: IntArray,
        val outs: IntArray,
    )

    private fun i32(b: ByteArray, p: Int): Int =
        (b[p].toInt() and 0xff) or ((b[p + 1].toInt() and 0xff) shl 8) or
        ((b[p + 2].toInt() and 0xff) shl 16) or ((b[p + 3].toInt() and 0xff) shl 24)

    /** Parse a circuit blob (TITANCIR or PFCTYPED). Returns null if the magic is unknown. */
    fun parse(b: ByteArray): Circuit? {
        if (b.size < 24) return null
        val magic = String(b, 0, 8, Charsets.US_ASCII)
        val nIn = i32(b, 8); val nWire = i32(b, 12); val nGate = i32(b, 16); val nOut = i32(b, 20)
        var p = 24
        return when (magic) {
            "TITANCIR" -> {
                val ga = IntArray(nGate); val gb = IntArray(nGate)
                for (i in 0 until nGate) { ga[i] = i32(b, p); p += 4 }
                for (i in 0 until nGate) { gb[i] = i32(b, p); p += 4 }
                val outs = IntArray(nOut); for (i in 0 until nOut) { outs[i] = i32(b, p); p += 4 }
                Circuit(nIn, nWire, nGate, nOut, false, IntArray(0), ga, gb, outs)
            }
            "PFCTYPED" -> {
                val op = IntArray(nGate); val ga = IntArray(nGate); val gb = IntArray(nGate)
                for (i in 0 until nGate) { op[i] = b[p].toInt() and 0xff; ga[i] = i32(b, p + 1); gb[i] = i32(b, p + 5); p += 9 }
                val outs = IntArray(nOut); for (i in 0 until nOut) { outs[i] = i32(b, p); p += 4 }
                Circuit(nIn, nWire, nGate, nOut, true, op, ga, gb, outs)
            }
            else -> null
        }
    }

    fun parseFile(path: String): Circuit? = try { parse(File(path).readBytes()) } catch (_: Throwable) { null }

    /** Ripple the circuit once for the given input bits (length must be <= nIn; missing inputs default 0). Byte-exact. */
    fun eval(c: Circuit, inputs: BooleanArray): BooleanArray {
        val v = BooleanArray(c.nWire)
        v[1] = true                                   // const1
        val base = 2 + c.nIn
        for (i in 0 until c.nIn) v[2 + i] = i < inputs.size && inputs[i]
        if (c.typed) {
            for (i in 0 until c.nGate) {
                val a = v[c.ga[i]]; val b = v[c.gb[i]]
                v[base + i] = when (c.op[i]) {
                    0 -> !(a && b); 1 -> a && b; 2 -> a || b; 3 -> a != b; else -> !a   // 4 = NOT
                }
            }
        } else {
            for (i in 0 until c.nGate) v[base + i] = !(v[c.ga[i]] && v[c.gb[i]])         // NAND
        }
        return BooleanArray(c.nOut) { v[c.outs[it]] }
    }

    // ── integer helpers: pack operands LSB-first into input bits, read the output bits back as an integer ──
    fun bitsOf(value: Long, width: Int): BooleanArray = BooleanArray(width) { ((value shr it) and 1L) == 1L }

    fun toLong(bits: BooleanArray): Long { var r = 0L; for (i in bits.indices) if (bits[i]) r = r or (1L shl i); return r }

    /** Concatenate several LSB-first operand fields into one input vector, in order (matches fabrication convention). */
    fun packOperands(vararg fields: Pair<Long, Int>): BooleanArray {
        var total = 0; for (f in fields) total += f.second
        val out = BooleanArray(total); var off = 0
        for ((value, width) in fields) { for (k in 0 until width) out[off + k] = ((value shr k) and 1L) == 1L; off += width }
        return out
    }
}
