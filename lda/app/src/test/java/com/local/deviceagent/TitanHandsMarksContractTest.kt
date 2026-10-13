package com.local.deviceagent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Pins actual owner-path delegation: AgentBrain.toJpegBytes calls TitanHandsMarks.overlay
 * and no longer carries a second drawMarks/drawGrid/downscale algorithm.
 */
class TitanHandsMarksContractTest {

    @Test fun testOwnerPathDelegatesToCanonicalTitanHandsMarks() {
        val brain = readSource("AgentBrain.kt")
        val marks = readSource("TitanHandsMarks.kt")
        assertTrue(brain.contains("TitanHandsMarks.overlay("))
        assertTrue(brain.contains("drawLastTap("))
        assertFalse(brain.contains("private fun drawMarks("))
        assertFalse(brain.contains("private fun drawGrid("))
        assertFalse(brain.contains("private fun downscale("))
        assertTrue(marks.contains("fun overlay("))
        assertTrue(marks.contains("private fun drawMarks("))
        assertTrue(marks.contains("private fun drawGrid("))
        assertTrue(marks.contains("private fun downscale("))
        assertEqualsOneAlgorithm(marks)
    }

    private fun assertEqualsOneAlgorithm(marks: String) {
        val draws = Regex("private fun drawMarks\\(").findAll(marks).count()
        val grids = Regex("private fun drawGrid\\(").findAll(marks).count()
        val scales = Regex("private fun downscale\\(").findAll(marks).count()
        assertTrue("expected one drawMarks in TitanHandsMarks, found $draws", draws == 1)
        assertTrue("expected one drawGrid in TitanHandsMarks, found $grids", grids == 1)
        assertTrue("expected one downscale in TitanHandsMarks, found $scales", scales == 1)
    }

    private fun readSource(name: String): String {
        var dir = File(System.getProperty("user.dir"))
        repeat(8) {
            val candidates = listOf(
                File(dir, "src/main/java/com/local/deviceagent/$name"),
                File(dir, "app/src/main/java/com/local/deviceagent/$name"),
                File(dir, "lda/app/src/main/java/com/local/deviceagent/$name"),
            )
            candidates.firstOrNull { it.isFile }?.let { return it.readText() }
            dir = dir.parentFile ?: return@repeat
        }
        throw AssertionError("$name not found from ${System.getProperty("user.dir")}")
    }
}
