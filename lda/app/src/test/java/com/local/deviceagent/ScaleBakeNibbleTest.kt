package com.local.deviceagent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Rung 0 guard for the int4 bake sign bug. LiteRT int4 weights are signed-symmetric: code n∈0..15 ↔ value
 * (n<8 ? n : n−16), range −8..7. The old bake nudged the raw 0..15 code and clamped 0..15, so a +1 on code 7 (=+7)
 * rolled to code 8 (=−8) — a −15 catastrophic flip that made every FFN nudge self-defeating (the confirmed no-op root
 * cause). These tests assert the fixed `nudgeSignedNibble` moves the WEIGHT VALUE by exactly `step` (clamped to the real
 * range) and NEVER jumps by more than |step| — i.e. no wrap, no discontinuity.
 */
class ScaleBakeNibbleTest {

    /** decode a 4-bit code to its signed int4 value. */
    private fun sval(code: Int): Int = (code and 0xF).let { if (it < 8) it else it - 16 }

    @Test
    fun nudge_moves_value_by_exactly_step_clamped() {
        for (code in 0..15) {
            for (step in intArrayOf(1, 2, 3, -1, -2, -3)) {
                val outCode = ScaleBake.nudgeSignedNibble(code, step)
                val before = sval(code)
                val after = sval(outCode)
                val expected = (before + step).coerceIn(-8, 7)
                assertEquals("code $code step $step: value should move to $expected", expected, after)
            }
        }
    }

    @Test
    fun nudge_never_jumps_more_than_step() {
        // the exact failure mode of the old bug: +1 on code 7 must NOT become −8 (a 15-magnitude jump).
        for (code in 0..15) {
            for (step in intArrayOf(1, 2, 3, -1, -2, -3)) {
                val outCode = ScaleBake.nudgeSignedNibble(code, step)
                val delta = kotlin.math.abs(sval(outCode) - sval(code))
                assertTrue("code $code step $step jumped by $delta (> ${kotlin.math.abs(step)})",
                    delta <= kotlin.math.abs(step))
            }
        }
        // spot-check the exact bug: +1 on code 7 (=+7) must stay +7 (clamped), NOT flip to −8.
        assertEquals(7, sval(ScaleBake.nudgeSignedNibble(7, 1)))
        // −1 on code 8 (=−8) must stay −8 (clamped), NOT flip to +7.
        assertEquals(-8, sval(ScaleBake.nudgeSignedNibble(8, -1)))
    }

    @Test
    fun output_is_a_valid_4bit_code() {
        for (code in 0..15) for (step in -3..3) {
            val out = ScaleBake.nudgeSignedNibble(code, step)
            assertTrue("output $out out of 0..15", out in 0..15)
        }
    }
}
