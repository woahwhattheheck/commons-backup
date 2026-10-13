package com.local.deviceagent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Named regressions for TITAN capture same-generation binding and the TITAN-side
 * Set-of-Marks numbering/constants contract. Pure JVM: no Bitmap, no device.
 */
class TitanHandsMarksGenerationTest {

    private fun token(
        snapshot: String,
        ids: List<Int> = listOf(0, 3),
        boxes: List<IntArray> = listOf(intArrayOf(0, 0, 40, 40), intArrayOf(80, 10, 120, 50)),
        w: Int = 1080,
        h: Int = 1920,
    ): String = TitanHandsMarks.generationToken(snapshot, ids, boxes, w, h)

    @Test fun testSameGenerationBindsSemanticsAndMarks() {
        val before = token("[0] Save\n[3] Cancel")
        val after = token("[0] Save\n[3] Cancel")
        assertEquals(before, after)
        assertEquals(before, TitanHandsMarks.sameGenerationOrNull(before, after))
    }

    @Test fun testUnrelatedSemanticsAreTypedMismatch() {
        val before = token("[0] Save")
        val after = token("[0] Different window")
        assertNotEquals(before, after)
        assertNull(TitanHandsMarks.sameGenerationOrNull(before, after))
        assertEquals("SCREEN_GENERATION_MISMATCH", TitanHandsMarks.GENERATION_MISMATCH_REASON)
    }

    @Test fun testBoxDriftIsTypedMismatch() {
        val before = token("[0] Save", boxes = listOf(intArrayOf(0, 0, 40, 40), intArrayOf(80, 10, 120, 50)))
        val after = token("[0] Save", boxes = listOf(intArrayOf(0, 0, 40, 40), intArrayOf(8, 10, 120, 50)))
        assertNotEquals(before, after)
        assertNull(TitanHandsMarks.sameGenerationOrNull(before, after))
    }

    @Test fun testMarkIdDriftIsTypedMismatch() {
        val before = token("[0] Save", ids = listOf(0, 3))
        val after = token("[0] Save", ids = listOf(0, 4))
        assertNotEquals(before, after)
        assertNull(TitanHandsMarks.sameGenerationOrNull(before, after))
    }

    @Test fun testEmptyGenerationIsNotAtomic() {
        assertNull(TitanHandsMarks.sameGenerationOrNull("", ""))
        assertNull(TitanHandsMarks.sameGenerationOrNull("abc", ""))
        assertNull(TitanHandsMarks.sameGenerationOrNull("", "abc"))
    }

    @Test fun testNumberingContractUsesGridSpecAndRealIds() {
        assertEquals(8, GridSpec.COLS)
        assertEquals(12, GridSpec.ROWS)
        assertEquals(640, TitanHandsMarks.DEFAULT_MAX_PX)
        assertEquals(60, TitanHandsMarks.DEFAULT_JPEG_QUALITY)
        assertEquals("image/jpeg", TitanHandsMarks.JPEG_MIME)
        assertEquals("jpeg", TitanHandsMarks.JPEG_FORMAT)
        assertEquals(".jpg", TitanHandsMarks.JPEG_SUFFIX)
    }
}
