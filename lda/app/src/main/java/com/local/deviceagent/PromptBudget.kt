package com.local.deviceagent

/**
 * Unified prompt-context budget: the many knowledge blocks we inject (values, facts, lessons,
 * situation-recall, mistakes, failure-recall, nav-map, device profile) all draw from ONE budget and
 * ACCOUNT FOR EACH OTHER, instead of each independently deciding to include itself. Two rules:
 *
 *  1. PRIORITY, not first-come. Blocks are admitted highest-priority first until the char budget
 *     runs out, so on a tight budget the agent keeps its VALUES and what-worked-HERE over a generic
 *     device profile - the important context survives, the marginal context is what gets dropped.
 *  2. DEDUP. A block whose content is already substantially covered by an admitted higher-priority
 *     block is dropped as redundant (a value and a lesson that say the same thing, a failure-recall
 *     and a failure-lesson about the same run) - so the systems stop repeating each other.
 *
 * This is the coherence layer that keeps the growing set of memory systems from crowding each other
 * off the OOM-tight prompt (CLAUDE §8/§13). It never decides WHAT to do - it only decides which
 * already-built context fits, by a fixed priority the caller sets.
 */
object PromptBudget {

    data class Block(val key: String, val text: String, val priority: Int)

    data class Result(val text: String, val kept: List<String>, val dropped: List<String>)

    private fun norm(s: String): String =
        s.lowercase().replace(Regex("[^a-z0-9 ]"), " ").replace(Regex("\\s+"), " ").trim()

    /** True when [a]'s meaningful words are ≥80% already present in [b] - i.e. [a] is redundant
     *  given [b]. Short blocks (<4 content words) are never treated as covered (too little signal). */
    private fun coveredBy(a: String, b: String): Boolean {
        val wa = norm(a).split(' ').filter { it.length > 3 }.toSet()
        if (wa.size < 4) return false
        val wb = norm(b).split(' ').filter { it.length > 3 }.toSet()
        if (wb.isEmpty()) return false
        return wa.count { it in wb }.toFloat() / wa.size >= 0.8f
    }

    /** Admit the blocks that fit, priority-first, dropping redundant/over-budget ones. Output keeps
     *  the priority order (highest first). `dropped` tags each drop reason (dup/budget) for logging. */
    fun assemble(blocks: List<Block>, budgetChars: Int): Result {
        val ordered = blocks.filter { it.text.isNotBlank() }
            .sortedWith(compareByDescending { it.priority })
        val kept = ArrayList<Block>()
        val keptKeys = ArrayList<String>()
        val dropped = ArrayList<String>()
        var used = 0
        for (b in ordered) {
            when {
                kept.any { coveredBy(b.text, it.text) } -> dropped.add("${b.key}(dup)")
                used + b.text.length > budgetChars -> dropped.add("${b.key}(budget)")
                else -> { kept.add(b); keptKeys.add(b.key); used += b.text.length }
            }
        }
        return Result(kept.joinToString("\n") { it.text.trim() }, keptKeys, dropped)
    }

    // ---- INPUT / CONTEXT PRESSURE (a CAR job: measurable state, SURFACED - never a decision) --------
    // These feed the limit-awareness REFLEX (AgentOrchestrator's orient line) and the FOCUS operator's
    // no-inference side-effect. They only MEASURE how close the model's INPUT is to a limit and word a
    // suggestion the agent MAY read; they never change the action or force FOCUS (§2). Home is here
    // because it's the same tier-aware char-budget math the memory assembler above already owns.

    /** The per-device-tier SCREEN-TEXT ceiling in chars: roughly how much raw element-list text the
     *  vision decision can carry before the whole prompt courts the 4096-token overflow that blinds
     *  vision and forces the lean-retry (§8/§13). The bigger sibling of the "dense" cutoff (700/1000):
     *  dense is where the OPTIONAL memory blocks shed; THIS is where the screen text ITSELF is near the
     *  hard input limit even after they're gone. Ordered by the same tier logic the memory budget uses -
     *  a LEAN phone overflows sooner (less real room), the Fold (RICH) has the most.
     *  RESERVED_OUTPUT_CHARS is a SOFT headroom nudge for the decode cap (AgentBrain.capFor): the KV cache
     *  is shared input+output, so keeping the "peek in smaller increments" reflex firing a little sooner on a
     *  dense screen leaves room for the bounded output and steers the model to chunk (find/peek still reach
     *  everything - §12, nothing is hidden). This is advisory only; the HARD output bound is capFor/CapReached
     *  in AgentBrain.generate(). */
    private const val RESERVED_OUTPUT_CHARS = 512
    fun screenInputCeiling(tier: DeviceStats.DeviceTier): Int = when (tier) {
        DeviceStats.DeviceTier.LEAN -> 2600
        DeviceStats.DeviceTier.MID -> 3400
        DeviceStats.DeviceTier.RICH -> 4200
    } - RESERVED_OUTPUT_CHARS

    /** LIMIT-AWARENESS READING for the reflex: from signals the loop already has - the on-screen element
     *  COUNT, the screen text length vs this tier's input ceiling, and the accumulated-history length -
     *  return a concrete reading + a chunk-it suggestion the agent can READ, or "" when the input is NOT
     *  near a limit (so the reflex fires only on a genuinely overwhelming screen, never a normal one).
     *  Two independent close-calls, either trips it:
     *   (1) the screen text alone is >=85% of the ceiling - the prompt will shed every optional block and
     *       STILL sit near the hard token cap, i.e. blinded vision / a forced lean-retry is imminent;
     *   (2) the element list is so long (>=45 targets) the small model can't reliably GROUND its pick in
     *       it - perception overload that hurts well UNDER the token cap.
     *  A big accumulated history compounds it (less headroom left for the screen), so it lowers the
     *  element bar. This SURFACES pressure; it never edits the action or forces a move (§2). */
    fun inputPressure(screenChars: Int, elCount: Int, tier: DeviceStats.DeviceTier, historyChars: Int): String {
        val ceiling = screenInputCeiling(tier)
        val pct = if (ceiling > 0) (screenChars * 100) / ceiling else 0
        val heavyHistory = historyChars >= 1400
        val elBar = if (heavyHistory) 38 else 45
        val nearTokens = pct >= 85
        val tooManyEls = elCount >= elBar
        if (!nearTokens && !tooManyEls) return ""
        val why = when {
            tooManyEls && nearTokens -> "$elCount elements, ~$pct% of the input budget"
            tooManyEls -> "$elCount elements to ground a pick in"
            else -> "~$pct% of the input budget"
        }
        // R1: this rides in the orient HIGH (survives lean-retry's orient.take(400)) on exactly the
        // overflowing screens, so keep it SHORT - the verbose ~326-ch form was itself feeding the overflow.
        return "⚠ BIG SCREEN ($why) - {\"action\":\"peek\",\"region\":\"top/bottom/left/right/center/corner\"} " +
            "or find/scroll to ONE target; name the ONE thing that matters and act."
    }

    /** FOCUS operator's no-inference side-effect (mirrors DOUBT's memory-read pattern): a concrete
     *  chunking suggestion for THIS screen once the model CHOSE to focus - how many controls are here and
     *  how to take them in small bites (peek a region / find / page) instead of scanning the whole list,
     *  plus the drop-stale-assumptions half for the accumulated context. Pure perception from the element
     *  count; never decides the action (§2). */
    fun focusHint(elCount: Int): String =
        if (elCount >= 8)
            "$elCount controls here - don't scan them all: PEEK ONE region first ({\"action\":\"peek\",\"region\":\"top/bottom/left/right/center/a corner\"}) or {\"action\":\"find\",\"text\":\"...\"} the single control you need, page/scroll for the rest. Keep only the ONE thing that matters for the goal, and drop any stale assumption carried from earlier steps."
        else
            "Keep only the ONE fact on this screen that matters for the goal; drop the rest and any stale assumption carried from earlier steps, then act."
}
