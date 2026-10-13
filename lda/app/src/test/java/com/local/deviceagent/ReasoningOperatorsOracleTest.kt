package com.local.deviceagent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM unit tests for the single-model EXACTNESS ORACLE (U1) — ReasoningOperators.hasCheckableRule /
 * checkRuleSatisfied. This is the load-bearing lever that makes SCHEMA, REGROUND, and the refuse-to-
 * hallucinate family first-class bakeable targets, so a regression here silently corrupts the exactness
 * signal every downstream bake rides on. Three families, each asserted for a HELD case and an ESCAPED case,
 * plus the conservative-never-a-false-escape contract for an un-instrumented caller.
 */
class ReasoningOperatorsOracleTest {

    // ---- family membership ------------------------------------------------------------------------
    @Test fun checkableFamiliesAreRecognized() {
        assertTrue(ReasoningOperators.hasCheckableRule(ReasoningOperators.EVIDENCE))
        assertTrue(ReasoningOperators.hasCheckableRule(ReasoningOperators.SCHEMA))
        assertTrue(ReasoningOperators.hasCheckableRule(ReasoningOperators.REGROUND))
        assertTrue(ReasoningOperators.hasCheckableRule("EXPLORE"))  // N1: EXPLORE is anti-loop too
        assertTrue(ReasoningOperators.hasCheckableRule(ReasoningOperators.VERB))  // P1: verb-usage is verb-membership checkable
        assertTrue(ReasoningOperators.hasCheckableRule("schema"))   // case-insensitive
        // An operator with no single-model oracle yet must NOT claim to be checkable (else a false ✓ in σ).
        assertFalse(ReasoningOperators.hasCheckableRule(ReasoningOperators.DIRECT))
        assertFalse(ReasoningOperators.hasCheckableRule(ReasoningOperators.MIRROR))
        // P1: LAYOUT is bakeable via σ-off residency, NOT verb-membership — it must NOT claim a cheap oracle.
        assertFalse(ReasoningOperators.hasCheckableRule(ReasoningOperators.LAYOUT))
    }

    // ---- N1: SCHEMA is a live, electable operator with a formal rule -------------------------------
    @Test fun schemaOperatorIsInTheMenuAndBinds() {
        val menu = ReasoningOperators.menuText(emptyList())
        assertTrue("SCHEMA must be electable from the menu", menu.contains("SCHEMA:"))
        val schema = ReasoningOperators.BAKED.first { it.name == "SCHEMA" }
        assertTrue("SCHEMA must carry a formal binding rule", schema.rule.isNotBlank())
    }

    // ---- N2: NAVIGATE is a live, electable operator bound to the world-model, in the ADVANCE composite -----
    @Test fun navigateOperatorIsInTheMenuAndBinds() {
        val menu = ReasoningOperators.menuText(emptyList())
        assertTrue("NAVIGATE must be electable from the menu", menu.contains("NAVIGATE:"))
        val nav = ReasoningOperators.BAKED.first { it.name == "NAVIGATE" }
        assertTrue("NAVIGATE must carry a formal binding rule", nav.rule.isNotBlank())
        // It lives in ADVANCE (forward-progress) so it gets that stance + can stack with same-composite ops.
        assertTrue(ReasoningOperators.parentComposite("NAVIGATE").equals("ADVANCE", ignoreCase = true))
    }

    // ---- P1: VERB + LAYOUT are live action-layer capability operators -----------------------------
    @Test fun verbAndLayoutOperatorsAreInTheMenuAndBind() {
        val menu = ReasoningOperators.menuText(emptyList())
        assertTrue("VERB must be electable from the menu", menu.contains("VERB:"))
        assertTrue("LAYOUT must be electable from the menu", menu.contains("LAYOUT:"))
        assertTrue(ReasoningOperators.BAKED.first { it.name == "VERB" }.rule.isNotBlank())
        assertTrue(ReasoningOperators.BAKED.first { it.name == "LAYOUT" }.rule.isNotBlank())
        // The four action-layer capabilities are the bake target set (P1–P3).
        assertTrue(ReasoningOperators.ACTION_LAYER.containsAll(setOf("SCHEMA", "NAVIGATE", "VERB", "LAYOUT")))
    }

    // ---- NEW: per-metric reasoning operators (PROGRESS/SPEED/THRIFT) are electable + composed -----
    @Test fun newPerMetricOperatorsAreElectableAndComposed() {
        val menu = ReasoningOperators.menuText(emptyList())
        for (op in listOf("PROGRESS", "SPEED", "THRIFT")) {
            assertTrue("$op must be electable from the menu", menu.contains("$op:"))
            assertTrue("$op must carry a formal binding rule", ReasoningOperators.BAKED.first { it.name == op }.rule.isNotBlank())
        }
        assertTrue(ReasoningOperators.parentComposite("PROGRESS").equals("ADVANCE", ignoreCase = true))
        assertTrue(ReasoningOperators.parentComposite("SPEED").equals("RESOURCE", ignoreCase = true))
        assertTrue(ReasoningOperators.parentComposite("THRIFT").equals("RESOURCE", ignoreCase = true))
    }

    // ---- NEW: the always-on base layers (GUARD/ALIGN/CERTAIN) BAKE but are NOT electable ----------
    @Test fun baseLayersAreAlwaysOnNotElectable() {
        val saved = ReasoningOperators.distilledOps
        try {
            ReasoningOperators.distilledOps = emptySet()
            val menu = ReasoningOperators.menuText(emptyList())
            for (bl in ReasoningOperators.BASE_LAYERS) {
                assertFalse("$bl is an always-on base layer, must NOT be electable", menu.contains("$bl:"))
                assertTrue("$bl must carry a rule (it bakes)", ReasoningOperators.BAKED.first { it.name.equals(bl, true) }.rule.isNotBlank())
                assertTrue("$bl must be in the defined install set (bakeable)", ReasoningOperators.definedInstallSet().any { it.equals(bl, true) })
            }
            // CERTAIN's no-guess is always injected under every decision.
            val block = ReasoningOperators.baseLayerBlock()
            assertTrue("base-layer block must carry the CERTAIN no-guess line", block.contains("CERTAIN") && block.contains("guess"))
        } finally { ReasoningOperators.distilledOps = saved }
    }

    // ---- P2: the drop-seam gate (bakedActionLayer = distilledOps ∩ ACTION_LAYER) ------------------
    @Test fun bakedActionLayerIntersectsDistilledWithActionLayer() {
        val saved = ReasoningOperators.distilledOps
        try {
            ReasoningOperators.distilledOps = emptySet()
            assertTrue("empty distilled => empty baked layer => byte-identical prompt",
                ReasoningOperators.bakedActionLayer().isEmpty())
            // A mix: an action-layer cap (VERB), a non-action-layer op (REFLECT), and a lowercase action-layer cap.
            ReasoningOperators.distilledOps = setOf("VERB", "REFLECT", "navigate")
            val baked = ReasoningOperators.bakedActionLayer()
            assertTrue("VERB" in baked)
            assertTrue("NAVIGATE" in baked)        // case-insensitive intersection
            assertFalse("REFLECT" in baked)        // a baked op that is NOT an action-layer capability is excluded
        } finally {
            ReasoningOperators.distilledOps = saved
        }
    }

    // ---- P1: VERB verb-membership exactness -------------------------------------------------------
    @Test fun verbHeldForRealExecutableVerb() {
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.VERB, """{"action":"click","id":5}""", screen = "", carried = ""))
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.VERB, """{"action":"open_app","name":"Gmail"}""", screen = "", carried = ""))
    }

    @Test fun verbEscapedForInventedVerb() {
        // "teleport" is not a real executor verb → the model invented one → escaped.
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.VERB, """{"action":"teleport","id":5}""", screen = "", carried = ""))
    }

    @Test fun verbConservativeWhenNoActionField() {
        // No parseable action field → never a false ESCAPE.
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.VERB, """{"id":5}""", screen = "", carried = ""))
    }

    // EXPLORE's loop-exactness: a repeat of a dead move ESCAPES; a fresh move HOLDS.
    @Test fun exploreLoopExactnessMatchesReground() {
        val tried = listOf("clicked Send")
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            "EXPLORE", "{}", screen = "", carried = "", triedActions = tried, actionKey = "clicked Send"))
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            "EXPLORE", "{}", screen = "", carried = "", triedActions = tried, actionKey = "opened menu"))
    }

    // ---- EVIDENCE (grounding) ---------------------------------------------------------------------
    @Test fun evidenceHeldWhenDigitTokenIsGrounded() {
        val action = """{"action":"set_text","id":3,"text":"Balance is 452 dollars"}"""
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.EVIDENCE, action, screen = "Account balance 452", carried = "", objective = ""))
    }

    @Test fun evidenceEscapedWhenDigitTokenIsInvented() {
        // 999 appears nowhere on screen / in the carried value / in the objective → the model invented it.
        val action = """{"action":"set_text","id":3,"text":"Send code 999"}"""
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.EVIDENCE, action, screen = "Enter the code we texted you", carried = "", objective = ""))
    }

    @Test fun evidencePureProseIsExempt() {
        // No digit-bearing token → creative prose, always held (§2: the standard governs values, not creativity).
        val action = """{"action":"reply","message":"I respectfully disagree with that stance."}"""
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.EVIDENCE, action, screen = "debate", carried = "", objective = ""))
    }

    // ---- SCHEMA (output-binding / clean JSON) -----------------------------------------------------
    @Test fun schemaHeldForCleanActionJson() {
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.SCHEMA, """{"action":"click","id":5}""", screen = "", carried = ""))
    }

    @Test fun schemaHeldWithLeadingThoughtObject() {
        // A tiny thought INSIDE the first object is fine — it still strict-parses and has an action.
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.SCHEMA, """{"thought":"tap send","action":"click","id":5}""", screen = "", carried = ""))
    }

    @Test fun schemaEscapedForSalvageNeededJson() {
        // The forms that FORCE the executor's regex-rebuild salvage (org.json rejects them) → NOT clean → escaped:
        // a doubled-verb mis-key, and an unterminated string (the model-spiral shape).
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.SCHEMA, """{"action":"set_text":"hello"}""", screen = "", carried = ""))
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.SCHEMA, """{"action":"click","text":"hello""", screen = "", carried = ""))
    }

    @Test fun schemaEscapedForObjectWithoutAction() {
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.SCHEMA, """{"id":5}""", screen = "", carried = ""))
    }

    // ---- REGROUND (anti-loop) ---------------------------------------------------------------------
    @Test fun regroundEscapedWhenMoveRepeatsADeadAction() {
        val tried = listOf("clicked Send", "tap search")
        assertFalse(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.REGROUND, "{}", screen = "", carried = "",
            triedActions = tried, actionKey = "clicked Send"))
    }

    @Test fun regroundHeldWhenMoveIsFresh() {
        val tried = listOf("clicked Send", "tap search")
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.REGROUND, "{}", screen = "", carried = "",
            triedActions = tried, actionKey = "opened menu"))
    }

    @Test fun regroundConservativeWhenInputsAbsent() {
        // No action key / no tried-set (an un-instrumented caller) → never a false ESCAPE.
        assertTrue(ReasoningOperators.checkRuleSatisfied(ReasoningOperators.REGROUND, "{}", screen = "", carried = ""))
    }

    // ---- the never-false-escape floor for a non-checkable op --------------------------------------
    @Test fun nonCheckableOperatorAlwaysHeld() {
        assertTrue(ReasoningOperators.checkRuleSatisfied(
            ReasoningOperators.DIRECT, """{"action":"click","id":5,}""", screen = "", carried = ""))
    }

    // ---- SM4 (the fuel-fix): the ALWAYS-ON action-layer capture predicates ------------------------
    // KNOWN_VERBS is the discriminator the always-on VERB banking uses (verb ∈ KNOWN_VERBS ⇒ WIN, else CONTRAST).
    // A real executor verb MISSING from the set would bank a genuine win as a false CONTRAST → poison the bake
    // fuel with the exact opposite label. Assert the canonical action verbs are all present.
    @Test fun knownVerbsCoverTheCanonicalActionSpace() {
        val canonical = listOf(
            "click", "set_text", "clear", "long_press", "scroll", "swipe", "tap_xy", "tap_near", "tap_grid",
            "tap_sequence", "open_app", "back", "home", "recent_apps", "app_drawer", "enter", "notifications",
            "quick_settings", "search", "find", "copy", "paste", "read_clipboard", "get_text", "zoom", "ocr",
            "reply", "assert", "draw", "sketch", "save_note", "wait", "ask", "batch", "done")
        for (v in canonical)
            assertTrue("KNOWN_VERBS must contain the real executor verb '$v' (else always-on VERB banking mislabels a win as a contrast)",
                v in ReasoningOperators.KNOWN_VERBS)
    }

    // ---- PART R (v3, INV-82): the DEFINED-operator direct-install target set ----------------------
    // runDefinedBake iterates definedInstallSet() and installs each op's KNOWN operational state via
    // bakeOperatorDirect (reference-free). The set must be non-empty, must include the whole action layer
    // (the owner's "operators you define PLUS the action layer"), and every member must carry a formal rule
    // (bakeOperatorDirect SKIPs a ruleless op — so a rule-less member would silently never install).
    @Test fun definedInstallSetIsWellFormed() {
        val set = ReasoningOperators.definedInstallSet()
        assertTrue("the defined install set must be non-empty", set.isNotEmpty())
        // the action layer (SCHEMA/VERB/NAVIGATE/LAYOUT) is part of what the Bake button installs
        assertTrue("SCHEMA in the install set", set.any { it.equals("SCHEMA", true) })
        assertTrue("VERB in the install set", set.any { it.equals("VERB", true) })
        assertTrue("NAVIGATE in the install set", set.any { it.equals("NAVIGATE", true) })
        assertTrue("LAYOUT in the install set", set.any { it.equals("LAYOUT", true) })
        // every installable op resolves to a non-blank formal rule (else bakeOperatorDirect can't build the σ-ON probe)
        for (op in set) assertTrue("$op must have a formal rule to be installable", ReasoningOperators.ruleOf(op).isNotBlank())
        // no duplicates (distinct-by-name)
        assertTrue("no duplicate operators in the install set", set.size == set.map { it.uppercase() }.toSet().size)
    }

    @Test fun ruleOfReturnsTheFormalRuleAndBlankForUnknown() {
        assertTrue(ReasoningOperators.ruleOf("VERB").isNotBlank())
        assertTrue(ReasoningOperators.ruleOf("verb").isNotBlank())            // case-insensitive
        assertTrue(ReasoningOperators.ruleOf("NOT_AN_OPERATOR").isBlank())    // unknown → "" (bakeOperatorDirect SKIPs)
    }

    // The combined per-step discriminator: a clean action with a real verb is a PROVEN action-layer WIN on both
    // capabilities (VERB held ∧ SCHEMA held ⇒ two positive references); an invented-verb, salvage-needed action
    // is a CONTRAST on both (VERB escaped ∧ SCHEMA escaped ⇒ two negative references). This is exactly the
    // win/contrast decision bankActionLayerRefs makes each proven step.
    @Test fun alwaysOnCaptureClassifiesWinAndContrast() {
        val cleanRealVerb = """{"action":"click","id":5}"""
        assertTrue(ReasoningOperators.checkRuleSatisfied(ReasoningOperators.VERB, cleanRealVerb, "", ""))
        assertTrue(ReasoningOperators.checkRuleSatisfied(ReasoningOperators.SCHEMA, cleanRealVerb, "", ""))
        // Invented verb AND unterminated string (needs salvage) → both capabilities escape → contrast on both.
        val inventedDirty = """{"action":"teleport","text":"go"""
        assertFalse(ReasoningOperators.checkRuleSatisfied(ReasoningOperators.VERB, inventedDirty, "", ""))
        assertFalse(ReasoningOperators.checkRuleSatisfied(ReasoningOperators.SCHEMA, inventedDirty, "", ""))
    }
}
