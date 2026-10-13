package com.local.deviceagent

import android.content.Context

/**
 * EXACT-COMPUTE GROUNDING oracle (pfc x LDA fusion, docs/PFC_LDA_OPENINGS.md).
 *
 * Extracted PURE so it is unit-testable on-device (DiagReceiver --es exactground "run") and can touch NO
 * orchestrator state. It decides exactly ONE thing: is the model about to type an UNGROUNDED number that a clean,
 * UNAMBIGUOUS integer computation on the byte-exact pfc circuit (Sandbox.compute -> fabricated mul32/add32)
 * DEFINITELY contradicts? If so it returns a re-author NOTE; otherwise null.
 *
 * SAFETY (owner rule: "if the agent did not decide an action it cannot fire"): this NEVER fires an action and NEVER
 * rewrites a value. The caller's only response to a non-null note is a bounded KICKBACK the model reads and
 * re-decides on (the shipped evidence-kickback recipe). It is a grounding GATE that can only bounce, never actuate.
 * On agreement OR any ambiguity (no single ungrounded integer, no clean 2-operand expr, operand out of range) it
 * returns null and the existing verifyEvidence path is left byte-identical. Integer add/multiply only today;
 * decimals and other shapes fall through to null.
 */
object ExactCompute {

    // Both operands must be < 2^32 (the fabricated mul32/add32 circuit width) so the comparison is the byte-exact
    // circuit result, never the lossy Double fallback.
    private const val LIM = 1L shl 32

    /** Returns a re-author note iff a DEFINITE integer disagreement is proven; null on agreement OR any ambiguity. */
    fun disagreement(ctx: Context, raw: String, screen: String, carried: String, objective: String): String? {
        val verb = Regex("\"action\"\\s*:\\s*\"(\\w+)\"").find(raw)?.groupValues?.get(1)?.lowercase() ?: return null
        if (verb !in setOf("set_text", "type", "input", "enter_text", "settext", "save_note", "write_note", "send", "ask")) return null
        val payload = (Regex("\"(?:value|text|message|note|content)\"\\s*:\\s*\"([^\"]*)\"").find(raw)?.groupValues?.get(1)
            ?: return null).replace(",", "")
        // The asserted RESULT = the single integer token in the payload grounded NOWHERE (screen / carried /
        // objective) - a computed value, not a read one. 0 or >1 such tokens => ambiguous => bail.
        val hay = (screen + " " + carried + " " + objective).replace(",", "").lowercase()
        val ungrounded = Regex("(?<![\\d.])\\d{1,10}(?![\\d.])").findAll(payload).map { it.value }
            .filter { !hay.contains(it) }.distinct().toList()
        if (ungrounded.size != 1) return null
        val asserted = ungrounded[0].toLongOrNull() ?: return null
        val expr = recoverExpr(raw, screen, objective, payload, asserted) ?: return null
        val exact = Sandbox.compute(ctx, expr).toLongOrNull() ?: return null   // must be a clean integer result
        if (exact == asserted) return null                                     // the model computed it right - no bounce
        return "EXACT: a byte-exact on-device computation of \"$expr\" reads $exact, but you're about to enter " +
            "$asserted. Recompute and re-enter the correct value - do not type it from memory."
    }

    /** Recover a clean "A op B" (integer + or *, both operands < 2^32) ONLY when UNAMBIGUOUS; null otherwise
     *  (the safe default - an ambiguous recovery must never trigger a bounce). Two sources, in order. */
    private fun recoverExpr(raw: String, screen: String, objective: String, payload: String, asserted: Long): String? {
        fun clean(a: Long, op: String, b: Long): String? = if (a in 0L until LIM && b in 0L until LIM) "$a$op$b" else null
        // (a) the model SHOWED its work - a "thought"/"note"/"expr" of the form "A op B = C" where C is exactly the
        //     value it typed. Tying the expr to the asserted result makes it zero-ambiguity: we only check the
        //     model's OWN stated arithmetic, never guess what it meant.
        val work = Regex("\"(?:thought|note|reason|expr|calc)\"\\s*:\\s*\"([^\"]*)\"").find(raw)?.groupValues?.get(1)?.replace(",", "")
        if (work != null) {
            val m = Regex("(\\d{1,10})\\s*([*+×])\\s*(\\d{1,10})\\s*=\\s*(\\d{1,10})").find(work)
            if (m != null && m.groupValues[4].toLongOrNull() == asserted) {
                val op = if (m.groupValues[2] == "×") "*" else m.groupValues[2]
                return clean(m.groupValues[1].toLong(), op, m.groupValues[3].toLong())
            }
        }
        // (b) EXACTLY two distinct on-screen integers + an explicit ADDITION cue (total/sum/plus/...) in the payload
        //     or objective => operator AND operand-pair are both determined. Deliberately narrow: this is where the
        //     spec's named mis-parse risk lives, so anything else (!=2 ints, no explicit add cue, any multiplication
        //     ambiguity) => null. Bounce-only + self-relenting means even a rare mis-read is a bounded nudge.
        val hint = (payload + " " + objective).lowercase()
        if (listOf("total", "sum", "plus", "add", "altogether", "combined", " + ").any { hint.contains(it) }) {
            val ints = Regex("(?<![\\d.])\\d{1,9}(?![\\d.])").findAll(screen.replace(",", "")).map { it.value.toLong() }
                .filter { it < LIM }.distinct().toList()
            if (ints.size == 2) return clean(ints[0], "+", ints[1])
        }
        return null
    }

    /**
     * On-device self-test (DiagReceiver --es exactground "run"): synthetic cases through the REAL oracle. No phone
     * driving, no action ever fires - it only calls disagreement() and inspects the returned note/null. Proves:
     * (1) a wrong shown sum bounces, (2) a correct shown sum passes, (3) a wrong on-screen-derived total bounces,
     * (4) ambiguity (no shown work, no add-cue) passes through. Requires files/{mul32,add32}.pfc staged.
     */
    fun selfTest(ctx: Context): String {
        data class Case(val name: String, val raw: String, val screen: String, val obj: String, val expectBounce: Boolean)
        val cases = listOf(
            Case("wrong-shown-sum",    """{"action":"set_text","id":5,"text":"1560","thought":"1200+350=1560"}""", "cart", "enter the total", true),
            Case("correct-shown-sum",  """{"action":"set_text","id":5,"text":"1550","thought":"1200+350=1550"}""", "cart", "enter the total", false),
            Case("wrong-screen-total", """{"action":"set_text","id":5,"text":"45"}""", "item A 12  item B 34  subtotal", "enter the total", true),
            Case("ambiguous-no-work",  """{"action":"set_text","id":5,"text":"777"}""", "some numbers 3 5 9 12 20 44 here", "type a value", false)
        )
        val sb = StringBuilder()
        var pass = 0
        for (c in cases) {
            val note = try { disagreement(ctx, c.raw, c.screen, "", c.obj) } catch (t: Throwable) { "ERR:${t.message}" }
            val bounced = note != null
            val ok = bounced == c.expectBounce
            if (ok) pass++
            sb.append("\n  ${if (ok) "PASS" else "FAIL"} ${c.name}: ${if (bounced) "BOUNCE" else "pass-through"} " +
                "(expected ${if (c.expectBounce) "bounce" else "pass"})${if (bounced) " :: ${note.toString().take(70)}" else ""}")
        }
        return "exact-compute oracle self-test: $pass/${cases.size} PASS$sb"
    }
}
