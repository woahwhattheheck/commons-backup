package com.local.deviceagent

import android.content.Context

/**
 * THE CATALOG — AOS's filesystem / the agent's self-view (owner 07-12: "the Files-app view of myself… THAT is the
 * layer we are missing"). One browsable INDEX over every resource the agent can reach — operators, memory, exemplars,
 * baked capabilities — each carried as a CHEAP DESCRIPTOR (the "thumbnail"): what it is, its form, its status, its cost.
 * The map is cheap and always available; the territory (an operator's full σ, a memory's body) is loaded on demand.
 *
 * This is the AOS KERNEL keystone: the router reads it to pick the cheapest resource for a step, memory browses it to
 * know what it HAS without injecting it, and the agent SEES its whole self through it. §2-clean: pure PERCEPTION the
 * agent reads — it never decides from the Catalog; the model still elects. Flag `catalog` (default ON; index-only).
 *
 * Reuses what exists: ReasoningOperators (BAKED + distilledOps + libraryDigest), AgentMemory (facts/lessons/skills/
 * observations), ExemplarBank, ModelStore. Nothing new is stored — the Catalog is a VIEW.
 */
object Catalog {
    /** The FORM an operator is authored in — the 07-12 dialect finding surfaced as catalog metadata. */
    enum class Form { EXEMPLAR, LEAN, FORMAL, TAG }
    fun formOf(rule: String): Form = when {
        rule.isBlank() -> Form.TAG
        rule.contains("→") || Regex("\\}\\s*\\n").containsMatchIn(rule) -> Form.EXEMPLAR   // input→output demos
        rule.contains("∀") || rule.contains("Optimize:") || rule.contains("Priority:") -> Form.FORMAL   // 8-part σ
        else -> Form.LEAN
    }

    /** One operator's descriptor — the thumbnail. */
    data class OpCard(val name: String, val form: Form, val layer: String, val resident: Boolean, val whenToUse: String)

    fun operators(): List<OpCard> {
        val resident = try { ReasoningOperators.distilledOps.map { it.uppercase() }.toSet() } catch (_: Throwable) { emptySet() }
        return try {
            ReasoningOperators.BAKED.map { op ->
                val layer = when {
                    op.name in ReasoningOperators.BASE_LAYERS -> "base"
                    op.name in ReasoningOperators.ACTION_LAYER -> "action"
                    else -> "reasoning"
                }
                OpCard(op.name, formOf(op.rule), layer, op.name.uppercase() in resident, op.whenToUse.take(60))
            }
        } catch (_: Throwable) { emptyList() }
    }

    /** The full [catalog] block: the agent's self-view at a glance (index only; bodies loaded on demand). */
    fun dump(c: Context): String {
        val ops = operators()
        val byForm = ops.groupingBy { it.form }.eachCount()
        val byLayer = ops.groupingBy { it.layer }.eachCount()
        val resident = ops.count { it.resident }
        val sb = StringBuilder()
        sb.append("═══ CATALOG (the agent's self-view) ═══\n")
        sb.append("OPERATORS ${ops.size}: form{exemplar=${byForm[Form.EXEMPLAR] ?: 0} lean=${byForm[Form.LEAN] ?: 0} formal=${byForm[Form.FORMAL] ?: 0} tag=${byForm[Form.TAG] ?: 0}} " +
            "layer{base=${byLayer["base"] ?: 0} action=${byLayer["action"] ?: 0} reasoning=${byLayer["reasoning"] ?: 0}} resident=$resident\n")
        // the FORMAL ones are the conversion backlog (the sweep-convicted worksheet form) — surfaced so the work is visible
        val backlog = ops.filter { it.form == Form.FORMAL }.map { it.name }
        if (backlog.isNotEmpty()) sb.append("  → still FORMAL (convert to exemplar via the finder): ${backlog.joinToString(",")}\n")
        try {
            sb.append("MEMORY: facts=${AgentMemory.factsList(c).size} lessons=${AgentMemory.lessons(c).size} " +
                "skills=${AgentMemory.skills(c).size} observations=${AgentMemory.observations(c).size}\n")
        } catch (_: Throwable) { sb.append("MEMORY: (unavailable)\n") }
        try { sb.append("EXEMPLARS (own proven wins): ${ExemplarBank.count(c)}\n") } catch (_: Throwable) {}
        try { sb.append("REFERENCES (bake supervision): ${ReferenceStore.count(c)}\n") } catch (_: Throwable) {}
        sb.append("BAKED into W: $resident operators resident as ~1-token tags\n")
        sb.append("═══ END CATALOG ═══")
        return sb.toString()
    }

    /** The router's cheap read: for a step, the operators whose layer/relevance fit — the map the capability stack
     *  consults (§2-clean: the model still elects from it). Returns descriptors, never the full σ (load-on-demand). */
    fun routeCandidates(situationKind: String): List<OpCard> {
        val all = operators()
        // base + action layers always apply; reasoning ops are the electable set. The router narrows; the model picks.
        return all.filter { it.layer != "reasoning" } + all.filter { it.layer == "reasoning" }
    }
}
