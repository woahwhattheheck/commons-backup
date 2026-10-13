package com.local.deviceagent

import android.graphics.Bitmap
import android.graphics.Color

/**
 * Tiny perceptual fingerprint of a screenshot ("pixel map"), so the agent can tell whether the
 * screen ACTUALLY changed after an action - the signal the accessibility tree can't give on a
 * game/canvas (the tree is empty/static there, yet the pixels move). It's an average-hash: downscale
 * to 8x8 grayscale, one bit per cell for above/below the mean -> a 64-bit fingerprint. The Hamming
 * distance between two frames is a cheap "how much did it visibly change" measure (0 = identical,
 * ~64 = totally different). Cheap enough to run every step; robust to minor noise/animation.
 */
object PixelMap {
    private const val N = 8

    fun hash(bmp: Bitmap): Long {
        val small = try { Bitmap.createScaledBitmap(bmp, N, N, true) } catch (_: Exception) { return 0L }
        val lum = IntArray(N * N)
        var sum = 0L
        for (y in 0 until N) for (x in 0 until N) {
            val p = small.getPixel(x, y)
            val l = (Color.red(p) * 299 + Color.green(p) * 587 + Color.blue(p) * 114) / 1000
            lum[y * N + x] = l; sum += l
        }
        if (small !== bmp) small.recycle()
        val mean = sum / (N * N)
        var h = 0L
        for (i in lum.indices) if (lum[i] >= mean) h = h or (1L shl i)
        return h
    }

    /** 0 = identical, up to 64 = completely different. */
    fun distance(a: Long, b: Long): Int = java.lang.Long.bitCount(a xor b)

    /** Which of the 64 cells (8x8, row-major i = y*N + x) flipped between two average-hashes. */
    fun cellsChanged(a: Long, b: Long): List<Int> {
        val diff = a xor b
        val out = ArrayList<Int>()
        for (i in 0 until N * N) if ((diff shr i) and 1L == 1L) out.add(i)
        return out
    }

    /** Track 1 (continuous change-sense): the NAMED screen region where the pixels changed most between
     *  two frames - the token-free "what moved between snapshots" signal. Centroid of the changed 8x8
     *  cells -> a 3x3 named region whose names match the peek / parseZoomRegion vocabulary
     *  (top/bottom/left/right/center/corners). "" when nothing changed. Pure geometry, no allocation cost
     *  worth caring about; runs on the frame hashes the loop already keeps. */
    fun regionOfChange(a: Long, b: Long): String {
        val cells = cellsChanged(a, b)
        if (cells.isEmpty()) return ""
        var sx = 0; var sy = 0
        for (c in cells) { sx += c % N; sy += c / N }
        val cx = sx.toFloat() / cells.size; val cy = sy.toFloat() / cells.size
        val col = (cx / N * 3f).toInt().coerceIn(0, 2)
        val row = (cy / N * 3f).toInt().coerceIn(0, 2)
        val vert = when (row) { 0 -> "top"; 2 -> "bottom"; else -> "" }
        val horiz = when (col) { 0 -> "left"; 2 -> "right"; else -> "" }
        return listOf(vert, horiz).filter { it.isNotEmpty() }.joinToString("-").ifEmpty { "center" }
    }
}
