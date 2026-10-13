package com.local.deviceagent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM unit tests for PromptBudget — the OOM-safe context assembler (CLAUDE §8/§13). These guard the exact
 * behaviors a regression would silently break: PRIORITY-first admission (VALUES survive a tight budget over
 * a generic profile), the (budget)/(dup) drop reasons the log relies on, and the input-pressure reflex only
 * firing on a genuinely overwhelming screen. Pure Kotlin, no Android — the DeviceTier enum is a bare nested
 * enum, so referencing it doesn't initialize the Android-touching DeviceStats object.
 */
class PromptBudgetTest {

    @Test fun everythingFitsKeepsAllInPriorityOrder() {
        val r = PromptBudget.assemble(
            listOf(
                PromptBudget.Block("low", "aaa", 1),
                PromptBudget.Block("high", "bbb", 9),
                PromptBudget.Block("mid", "ccc", 5),
            ), budgetChars = 1000,
        )
        // Kept in descending priority, none dropped.
        assertEquals(listOf("high", "mid", "low"), r.kept)
        assertTrue(r.dropped.isEmpty())
        assertEquals("bbb\nccc\naaa", r.text)
    }

    @Test fun blankBlocksAreIgnored() {
        val r = PromptBudget.assemble(
            listOf(
                PromptBudget.Block("real", "hello", 5),
                PromptBudget.Block("blank", "   ", 9),
            ), budgetChars = 1000,
        )
        assertEquals(listOf("real"), r.kept)
        assertTrue(r.dropped.isEmpty())
    }

    @Test fun overBudgetDropsLowestPriorityWithBudgetReason() {
        // Two 10-char blocks, budget 12 → only the higher-priority one fits; the other is a (budget) drop.
        val r = PromptBudget.assemble(
            listOf(
                PromptBudget.Block("keepme", "0123456789", 9),
                PromptBudget.Block("dropme", "abcdefghij", 2),
            ), budgetChars = 12,
        )
        assertEquals(listOf("keepme"), r.kept)
        assertEquals(listOf("dropme(budget)"), r.dropped)
    }

    @Test fun redundantLowerPriorityBlockDroppedAsDup() {
        // The lower-priority block's content words are a subset of the admitted higher-priority one → (dup).
        val r = PromptBudget.assemble(
            listOf(
                PromptBudget.Block("values", "honesty patience kindness courage always", 9),
                PromptBudget.Block("lesson", "honesty patience kindness courage", 3),
            ), budgetChars = 10_000,
        )
        assertEquals(listOf("values"), r.kept)
        assertEquals(listOf("lesson(dup)"), r.dropped)
    }

    @Test fun shortBlockNeverCountedAsDuplicate() {
        // <4 content words → never "covered", so a terse distinct block is not falsely deduped away.
        val r = PromptBudget.assemble(
            listOf(
                PromptBudget.Block("big", "honesty patience kindness courage", 9),
                PromptBudget.Block("terse", "honesty patience", 3),
            ), budgetChars = 10_000,
        )
        assertTrue("terse" in r.kept)
        assertTrue(r.dropped.isEmpty())
    }

    @Test fun inputPressureSilentOnACalmScreen() {
        // Well under both bars (token % and element count) → no reflex text.
        assertEquals("", PromptBudget.inputPressure(
            screenChars = 200, elCount = 5, tier = DeviceStats.DeviceTier.RICH, historyChars = 0))
    }

    @Test fun inputPressureFiresNearTokenCeiling() {
        val ceiling = PromptBudget.screenInputCeiling(DeviceStats.DeviceTier.LEAN)
        val out = PromptBudget.inputPressure(
            screenChars = ceiling, elCount = 3, tier = DeviceStats.DeviceTier.LEAN, historyChars = 0)
        assertTrue(out.startsWith("⚠ BIG SCREEN"))
    }

    @Test fun inputPressureFiresOnTooManyElements() {
        val out = PromptBudget.inputPressure(
            screenChars = 10, elCount = 60, tier = DeviceStats.DeviceTier.RICH, historyChars = 0)
        assertTrue(out.contains("60 elements"))
    }

    @Test fun heavyHistoryLowersTheElementBar() {
        // 40 elements is under the calm bar (45) but over the heavy-history bar (38).
        val calm = PromptBudget.inputPressure(10, 40, DeviceStats.DeviceTier.RICH, historyChars = 0)
        val heavy = PromptBudget.inputPressure(10, 40, DeviceStats.DeviceTier.RICH, historyChars = 5000)
        assertEquals("", calm)
        assertFalse(heavy.isEmpty())
    }

    @Test fun tierCeilingsOrderLeanBelowRich() {
        assertTrue(PromptBudget.screenInputCeiling(DeviceStats.DeviceTier.LEAN)
            < PromptBudget.screenInputCeiling(DeviceStats.DeviceTier.RICH))
    }
}
