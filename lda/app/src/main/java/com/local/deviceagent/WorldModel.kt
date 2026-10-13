package com.local.deviceagent

import android.content.Context
import org.json.JSONObject

/**
 * A1 / JEPA PASSIVE WORLD MODEL — W1: the CURIOSITY LEDGER + the token-free predict/compare read.
 *
 * The world model learns to predict what the screen becomes. The cheapest form of that prediction already
 * exists: `AgentMemory.recordTransition` reconciles each observed (app, fromSig, action)→toSig edge against
 * the remembered one (Tesla-FSD predict/verify) and returns a status — "reinforced(✓)" (the model predicted
 * this successor correctly), "changed" (it MISPREDICTED — the same action lands elsewhere now), or "new" (no
 * prediction existed yet). That status IS the JEPA energy, computed at ZERO inference.
 *
 * W1 aggregates that energy per SCREEN-CLASS (the H-JEPA abstraction key from ScreenClass) into a CuriosityLedger:
 * per class we keep {n, hit, miss, novel}. From it we read (a) per-class prediction reliability and (b) the
 * WORST (most-uncertain) class — the curiosity signal that tells W4/W6 where the model predicts poorly and thus
 * where a bake earns the most (the paper's "reward uncertainty-reduction"). Pure bookkeeping over the agent's
 * OWN measured outcome (never on-screen text as truth) — §2/§3-clean, nothing leaves the device, no model touch.
 *
 * Flag `world_model` (default ON) gates whether the ledger is written; the ledger itself is tiny (≤10 fixed
 * classes) and rolls nothing. Later phases add the σ_predict decode (W2), the targeted bake (W4), and the
 * INFO_GAIN curriculum (W6) on top of this ledger.
 */
object WorldModel {
    private const val PREF = "world_model"
    private const val LEDGER = "curiosity"     // JSON {class: {n,hit,miss,novel}}

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    /** Prediction outcome for one observed transition, derived from recordTransition's status. */
    enum class Outcome { HIT, MISS, NOVEL, SKIP }

    /** Map recordTransition's returned status string to a prediction outcome. */
    fun outcomeOf(transitionStatus: String): Outcome {
        val s = transitionStatus.trim().lowercase()
        return when {
            s.startsWith("reinforced") -> Outcome.HIT      // the model predicted this successor
            s == "changed" -> Outcome.MISS                 // same action → different screen now = mispredict
            s == "new" -> Outcome.NOVEL                    // no prediction existed (a novel edge)
            else -> Outcome.SKIP                           // "" = not a navigation edge
        }
    }

    /** Ledger one observation of the world model's prediction reliability on [screenClass]. Guarded; O(1);
     *  bounded (only the ~10 fixed ScreenClass ids ever appear). Gated by the caller on the `world_model` flag. */
    @Synchronized
    fun observe(c: Context, screenClass: String, outcome: Outcome) {
        if (outcome == Outcome.SKIP || screenClass.isBlank()) return
        try {
            val root = try { JSONObject(prefs(c).getString(LEDGER, "{}") ?: "{}") } catch (_: Exception) { JSONObject() }
            val cell = root.optJSONObject(screenClass) ?: JSONObject()
            cell.put("n", cell.optInt("n", 0) + 1)
            when (outcome) {
                Outcome.HIT -> cell.put("hit", cell.optInt("hit", 0) + 1)
                Outcome.MISS -> cell.put("miss", cell.optInt("miss", 0) + 1)
                Outcome.NOVEL -> cell.put("novel", cell.optInt("novel", 0) + 1)
                else -> {}
            }
            root.put(screenClass, cell)
            prefs(c).edit().putString(LEDGER, root.toString()).apply()
            AgentLog.log("worldmodel", "$screenClass ${outcome.name.lowercase()} " +
                "(hit=${cell.optInt("hit")} miss=${cell.optInt("miss")} novel=${cell.optInt("novel")} n=${cell.optInt("n")})")
        } catch (_: Exception) {}
    }

    /** Prediction ENERGY (0..1) for a class = the fraction of observations the model did NOT correctly
     *  predict = (miss + novel) / n. High ⇒ the model predicts this class poorly ⇒ a strong bake/curiosity
     *  target. 0.0 when the class is unseen. */
    fun energy(c: Context, screenClass: String): Double {
        return try {
            val cell = JSONObject(prefs(c).getString(LEDGER, "{}") ?: "{}").optJSONObject(screenClass) ?: return 0.0
            val n = cell.optInt("n", 0); if (n == 0) return 0.0
            (cell.optInt("miss", 0) + cell.optInt("novel", 0)).toDouble() / n
        } catch (_: Exception) { 0.0 }
    }

    /** The WORST (highest-energy) class with ≥[minN] observations — where the world model is least reliable.
     *  The curiosity curriculum signal (W6): bake/gather-info there for the most learning per effort. Null if
     *  nothing has enough samples yet. */
    fun worstClass(c: Context, minN: Int = 4): Pair<String, Double>? {
        return try {
            val root = JSONObject(prefs(c).getString(LEDGER, "{}") ?: "{}")
            root.keys().asSequence().mapNotNull { k ->
                val cell = root.optJSONObject(k) ?: return@mapNotNull null
                val n = cell.optInt("n", 0); if (n < minN) return@mapNotNull null
                k to (cell.optInt("miss", 0) + cell.optInt("novel", 0)).toDouble() / n
            }.maxByOrNull { it.second }
        } catch (_: Exception) { null }
    }

    /** W6 (curiosity signal): is the world model UNCERTAIN about [screenClass] — either it has too few observations
     *  to be confident ([minSeen]) OR it predicts the class poorly (energy ≥ 0.5)? Surfaces the INFO_GAIN operator so
     *  the agent gathers information (read-only) before committing on an unfamiliar screen — the owner's "adaptability +
     *  information gathering is the huge lever on novel screens." Read-only; guarded; false on error (never blocks). */
    fun uncertain(c: Context, screenClass: String, minSeen: Int = 3): Boolean {
        if (screenClass.isBlank()) return false
        return try {
            val cell = JSONObject(prefs(c).getString(LEDGER, "{}") ?: "{}").optJSONObject(screenClass) ?: return true
            val n = cell.optInt("n", 0)
            if (n < minSeen) return true    // unfamiliar — too little evidence to act confidently here
            (cell.optInt("miss", 0) + cell.optInt("novel", 0)).toDouble() / n >= 0.5
        } catch (_: Exception) { false }
    }

    /** Compact owner readout: per-class prediction hit-rate, worst-first (where the model struggles to predict). */
    fun readout(c: Context, max: Int = 8): String {
        return try {
            val root = JSONObject(prefs(c).getString(LEDGER, "{}") ?: "{}")
            root.keys().asSequence().mapNotNull { k ->
                val cell = root.optJSONObject(k) ?: return@mapNotNull null
                val n = cell.optInt("n", 0); if (n == 0) return@mapNotNull null
                Triple(k, cell.optInt("hit", 0) * 100 / n, n)
            }.sortedBy { it.second }.take(max).joinToString(" ") { "${it.first}=${it.second}%/${it.third}" }
        } catch (_: Exception) { "" }
    }

    // ---- W2: the σ_predict PREDICTOR — the reference the world-model bake scores + installs ------------------------
    // The world model's prediction is emitted in the ACTION grammar so ResidencyScore.extractAction scores it with ZERO
    // new parsing: {"action":"predict","id":"<resulting screen-CLASS>","label":"<≤5 stable labels>"}. The reference's
    // stored `action` is GROUND TRUTH — the screen-class we ACTUALLY observed next — so σ-off agreement measures "does
    // the frozen model already predict reality", and the W4 bake raises it (JEPA energy → weights). Abstraction-keyed:
    // both the prompt's SCREEN CLASS and the target `id` are ScreenClass ids, never a per-app path (H-JEPA).

    /** The ≤[max] most-salient quoted labels from a snapshot's element list — the "what's on this screen" summary the
     *  predictor CONDITIONS on. Distinct + order-preserving; trivial 1-char noise dropped. Keeps variable content (the
     *  input is the real observed screen); the prediction TARGET is stripped by [stableLabels]. */
    fun topLabels(snapshot: String, max: Int = 5): String {
        return try {
            Regex("\"([^\"]{2,32})\"").findAll(snapshot).map { it.groupValues[1].trim() }
                .filter { it.isNotBlank() }.distinct().take(max).joinToString(", ")
        } catch (_: Exception) { "" }
    }

    /** W3 (latent-z marginalization): the ≤[max] STABLE labels only — variable content (clock times, dates, counts,
     *  prices, message bodies) stripped via [AgentMemory.looksLikeVariableContent]. This is what the world model
     *  PREDICTS: the JEPA insight that the predictable INVARIANT of a screen-class is learnable and worth baking, while
     *  the variable residual z is generated/clipboarded at runtime (accuracy-critical values via copy/paste + EVIDENCE,
     *  prose generated normally) and NEVER baked — so a bake can't overfit to a timestamp that will never recur. If a
     *  screen's salient labels are ALL variable, the target degrades to the screen-CLASS alone (still a valid, stable
     *  abstraction prediction), never brittle noise. */
    fun stableLabels(snapshot: String, max: Int = 5): String {
        return try {
            Regex("\"([^\"]{2,32})\"").findAll(snapshot).map { it.groupValues[1].trim() }
                .filter { it.isNotBlank() && !AgentMemory.looksLikeVariableContent(it) }
                .distinct().take(max).joinToString(", ")
        } catch (_: Exception) { "" }
    }

    /** The lean, text-only prompt for one world-model prediction (no screenshot needed — the from-screen is described
     *  in text, so decideFromFrozen replays it cheaply). The formal σ:PREDICT rule LEADS (math>words, σ FIRST — the
     *  operator principle) and BINDS the output to the predict grammar; the situation follows. */
    fun predictPrompt(app: String, fromClass: String, fromLabels: String, action: String): String =
        "Σ:PREDICT\n" +
        "class(s) := the abstract screen-class; f := the transition THIS phone realizes; stable := chrome that recurs, variable := times/counts/prices\n" +
        "∀ (screen s, action a): predict s' = f(class(s), a) from resident knowledge of how THIS phone behaves\n" +
        "Optimize: max(agreement with the observed next class) min(memorized-path reliance)\n" +
        "Priority: the stable screen-class + chrome > variable content\n" +
        "Never predict a memorized path; never put variable content in the label\n" +
        "Output := {\"action\":\"predict\",\"id\":\"<resulting screen-class>\",\"label\":\"<≤5 stable labels>\"} — ONE object, nothing else\n" +
        "APP: $app\nSCREEN CLASS: $fromClass\nON SCREEN: $fromLabels\nACTION TAKEN: $action\nPREDICT the resulting screen:"

    /** The GROUND-TRUTH prediction target — the screen-class we actually observed next + its stable labels — in the
     *  same predict grammar, so ResidencyScore.extractAction scores it unchanged (verb=predict, target=[toClass]). */
    fun predictTarget(toClass: String, toLabels: String): String =
        "{\"action\":\"predict\",\"id\":\"$toClass\",\"label\":\"${toLabels.replace("\"", "")}\"}"

    /** W8 (canvas generality): the lean prompt for a PIXEL prediction — the next screen's PERCEPTUAL HASH on a
     *  canvas/game/blind screen where there are no elements, only pixels. The target is `predictPixTarget(toHash)`;
     *  ResidencyScore scores it by Hamming distance (a near-match on the 64-bit hash counts). */
    fun pixPredictPrompt(app: String, screenClass: String, fromHashHex: String): String =
        "Σ:PREDICT_PIX\n" +
        "hash(s) := the 64-bit avg perceptual hash (hex) of a canvas/blind screen (no elements, only pixels)\n" +
        "∀ (canvas s, evolution): predict hash(s') from resident knowledge of how THIS canvas evolves\n" +
        "Optimize: min(Hamming distance to the observed next hash)\n" +
        "Priority: the perceptual invariant > exact bits (a near-match counts)\n" +
        "Never guess bits with no basis in how the canvas moves\n" +
        "Output := {\"action\":\"predict\",\"id\":\"<resulting 16-hex perceptual hash>\",\"label\":\"pixels\"} — ONE object, nothing else\n" +
        "APP: $app\nSCREEN CLASS: $screenClass\nCURRENT PERCEPTUAL HASH: $fromHashHex\nPREDICT the resulting hash:"

    /** The GROUND-TRUTH pixel target — the perceptual hash we actually observed next, as hex, in the predict grammar. */
    fun predictPixTarget(toHash: Long): String =
        "{\"action\":\"predict\",\"id\":\"${java.lang.Long.toHexString(toHash)}\",\"label\":\"pixels\"}"

    /** W5 (H-JEPA HIGH level): the lean prompt for a FLOW prediction — the LANDING screen-class of a multi-hop proven
     *  corridor of [hops] steps from [startClass]. Same predict grammar (scored unchanged), one abstraction level up:
     *  not "what is the next screen" but "where does this route LEAD". The target is `predictTarget(landingClass, …)`. */
    fun flowPredictPrompt(app: String, startClass: String, startLabels: String, hops: Int): String =
        "Σ:PREDICT_FLOW\n" +
        "corridor := a multi-hop route of ≥2 proven steps; landing := the screen-class the corridor REACHES\n" +
        "∀ corridor from screen s: predict landing(corridor) from resident knowledge of how THIS phone's navigation flows\n" +
        "Optimize: max(agreement with the observed landing class) min(memorized-path reliance)\n" +
        "Priority: the stable landing screen-class > variable content there\n" +
        "Never predict a memorized path; never put variable content in the label\n" +
        "Output := {\"action\":\"predict\",\"id\":\"<landing screen-class>\",\"label\":\"<≤5 stable labels there>\"} — ONE object, nothing else\n" +
        "APP: $app\nSTART SCREEN CLASS: $startClass\nSTART LABELS: $startLabels\nCORRIDOR LENGTH: $hops proven steps\n" +
        "PREDICT where this corridor lands:"

    /** Best-effort SCREEN-CLASS of a raw snapshot string (the describe() element list + TEXT layer). Used at the
     *  observe seam, where the full codec/keyboard signals aren't threaded — element count is derived from the
     *  "[N]" tap handles and the whole snapshot serves as the text layer. Falls back to package/marker signals. */
    fun classifyOf(pkg: String, snapshot: String): String {
        val elementCount = Regex("\\[\\d+\\]").findAll(snapshot).count()
        return ScreenClass.classify(pkg, codec = "", text = snapshot, elementCount = elementCount, keyboardUp = false)
    }

    /** Wipe the curiosity ledger (owner's "Clear all memory" — own prefs). */
    fun clear(c: Context) { try { prefs(c).edit().clear().apply() } catch (_: Throwable) {} }
}
