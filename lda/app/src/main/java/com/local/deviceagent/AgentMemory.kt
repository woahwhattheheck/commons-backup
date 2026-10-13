package com.local.deviceagent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Small, persistent, size-capped memory the agent carries across tasks and reboots.
 * Two kinds of memory, both stored as JSON in SharedPreferences:
 *
 *  - FACTS: a key -> value map of durable user/device facts the agent should know
 *    (e.g. "phone number" -> "555-1234", "home address" -> "..."). Set explicitly
 *    ("remember my number is ...") and recalled when a task needs them.
 *  - LESSONS: a capped, de-duplicated list of short things the agent learned by doing
 *    (e.g. "Block Blast shows only a SurfaceView - play with tap_xy"). This is the
 *    bounded first step toward self-improvement from experience.
 *
 * A compact [forPrompt] block is injected into the action prompt so the model can use
 * what it knows without re-deriving it every time. Everything stays on-device.
 */
object AgentMemory {
    private const val PREF = "agent_memory"
    private const val FACTS = "facts"
    private const val LESSONS = "lessons"
    private const val LOGINS = "logins"
    private const val SENDS = "send_recipes"
    private const val SEND_SKILLS = "send_skills"   // structural: the EXACT field+send control per app
    private const val IDENTITY = "identity"         // the agent's persistent, continuous self
    private const val SKILLS = "skills"
    private const val UNKNOWN = "unknown_actions"
    private const val APPS = "device_apps"
    private const val PROFILE = "device_profile"
    private const val OBS = "observations"
    private const val BAD = "bad_memories"
    private const val MISTAKES = "screen_mistakes"   // per app+screen-signature: actions that did nothing here
    private const val SIGHTINGS = "passive_sightings"
    private const val NAV = "nav_maps"            // per-app accumulated navigation destinations
    private const val MAX_NAV_APPS = 40
    private const val MAX_NAV_DESTS = 16
    private const val SEEN = "seen_screens"       // structural signatures of screens met per app (novelty)
    private const val MAX_SEEN_PER_APP = 60
    private const val MAX_SEEN_APPS = 40
    private const val SELFCLAIMS = "self_claims"  // captured (not blocked) self-modification / self-referential claims
    private const val MAX_SELFCLAIMS = 20
    // WORLD MODEL: per app+screen, the action->next-screen edges (screen navigation map). Distinct from
    // the operator layer's OP_TRANS ("op_transitions", operator->operator reasoning credit) - different
    // store, different purpose: this is WHERE actions go on the phone, OP_TRANS is HOW to think.
    private const val TRANS = "transitions"
    private const val MAX_TRANS_APPS = 40
    private const val MAX_TRANS_SCREENS = 30
    private const val MAX_TRANS_EDGES = 8
    private const val CHECKPOINT = "task_checkpoint"  // #10: interrupted-task state, to offer a resume
    private const val MAX_LESSONS = 25
    private const val MAX_LESSON_LEN = 160
    private const val MAX_LOGINS = 60
    private const val MAX_SKILLS = 40
    private const val MAX_SKILL_LEN = 1200
    private const val SKILL_PROTECT_AT = 3        // confirmations before an auto-skill becomes pinned
    private const val MAX_UNKNOWN = 30
    private const val VALUES = "values"           // owner-set character/priors - the TOP tier of memory
    private const val MAX_VALUES = 12
    private const val MAX_VALUE_LEN = 120
    // OPERATOR LAYER (docs/OPERATOR_LAYER.md): transition memory + reasoning cache. Surfaced recall the
    // model reads, NEVER a rule; size-capped/keyed like the rest of memory; inert when the layer is off.
    private const val OP_CREDIT = "op_credit"        // {app: {OP: {n, m}}}          running-avg M per operator
    private const val OP_TRANS = "op_transitions"    // {app: {"PREV>NEXT": {n, m}}}  running-avg M per transition
    private const val OP_SEQ = "op_sequences"        // [{name, seq, time}]           reasoning cache (per objective)
    private const val MAX_OP_APPS = 40
    private const val MAX_OP_KEYS = 24
    private const val MAX_OP_SEQ = 40
    // OWNER OPERATORS: the owner's OWN reasoning "moves" that JOIN the selectable operator menu -
    // the mirror of VALUES, but for the operator layer. Model-SELECTED clauses ("how to think"),
    // never forced actions or vetoes (§2): the only path from a stored move into a prompt is
    // inject()'s "HOW TO THINK NOW:" header, so there is NO route to an executed action. Owner-set
    // only (never learned), persistent + global (unlike the per-task moves the helper authors).
    private const val OP_OWNER = "op_owner"
    private const val MAX_OWNER_OPS = 8           // keep the menu legible for a small model (baked is 9)
    private const val MAX_OWNER_OP_NAME = 16      // one UPPERCASE word (like parseGenerated)
    private const val MAX_OWNER_OP_WHEN = 80      // the whenToUse blurb
    private const val MAX_OWNER_OP_DO = 140       // the clause body ("Think NAME: <do>")
    // W2 AGENT OPERATORS: moves the AGENT ITSELF authored and that EARNED their keep (a proven positive
    // reward). Persistent + global like OP_OWNER, but provenance = agent, and admitted/kept ONLY by
    // measured M (the survival gate; §2 grounded signal, not self-judgment). Same {n,w,d,time} row shape.
    private const val OP_AGENT = "op_agent"
    private const val MAX_AGENT_OPS = 8           // small: the library converges to the FEW moves that work
    // A1 ACCEPTANCE ORACLE (the compounding spine's foundation): a durable, ATTRIBUTED tally of agent-driven task
    // outcomes so the ONE metric (§12) can be split by which OPERATORS were credited and which FLAG CONFIG was
    // running - "is EVIDENCE actually helping? does operator_stacking move the needle?" - instead of one flat
    // rate. This is owner-facing telemetry AND the trustworthy fitness signal A5's weight keep-gate needs; it is
    // NEVER a prompt, never auto-tunes a constant, never selects an action (§2/§12). Owner-STOPPED tasks are
    // counted SEPARATELY (interrupted) so the owner intervening can't poison the attribution (his "0/20 is skewed
    // by my stops" note). {clean:{n,s}, interrupted:int, ops:{OP:{n,s}}, flags:{sig:{n,s}}}.
    private const val ORACLE = "oracle_ledger"
    private const val MAX_ORACLE_FLAGS = 24       // distinct flag-configs kept; the lowest-n evicted past the cap

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    // WEAK-TRIGGER (INV-46): the reasoning operators DISTILLED into the ACTIVE model (by an off-device
    // operator-distillation recipe), keyed by the model's fingerprint so a flag only applies to the model it
    // was distilled into. When an operator is here, ReasoningOperators.inject() emits only its short TAG (the
    // cheap summon) instead of the full clause/rule — the behavior is resident in W. After ANY model swap the
    // fingerprint no longer matches, so this returns empty => full clause => byte-identical (safe default).
    private const val DISTILLED_OPS = "distilled_ops"
    private const val DISTILLED_FP = "distilled_fp"

    fun setDistilledOperators(c: Context, names: Set<String>, fingerprint: String) {
        prefs(c).edit()
            .putString(DISTILLED_OPS, names.joinToString(",") { it.uppercase() })
            .putString(DISTILLED_FP, fingerprint).apply()
    }

    fun distilledOperators(c: Context, fingerprint: String): Set<String> {
        if (prefs(c).getString(DISTILLED_FP, "") != fingerprint) return emptySet()
        return (prefs(c).getString(DISTILLED_OPS, "") ?: "").split(",")
            .map { it.trim().uppercase() }.filter { it.isNotEmpty() }.toSet()
    }

    // INV-49 IMITATION FIT: a running self-estimate of how well the model predicts the OWNER's demonstrated
    // procedures (learn-from-watching). Each scored demonstration updates an exponential moving average of the
    // per-demo fit% + a count, so the owner can see "I currently predict your next step ~X% of the time" and it
    // moves as the model learns his habits. On-device only; a self-eval read-out, never a decision input.
    private const val IMIT_FIT = "imitation_fit_ema"   // 0..100 EMA of demo fit%
    private const val IMIT_N = "imitation_fit_n"       // number of demos scored

    /** Fold one scored demonstration's fit% into the running EMA (weight 0.35 on the newest, so ~3 demos to
     *  shift). `fit` in 0..100; ignored if <0 (the score couldn't run). Returns the new EMA. */
    fun recordImitationFit(c: Context, fit: Int): Int {
        if (fit < 0) return imitationFit(c)
        val p = prefs(c)
        val n = p.getInt(IMIT_N, 0)
        val prev = p.getInt(IMIT_FIT, -1)
        val ema = if (prev < 0 || n == 0) fit else ((prev * 65 + fit * 35) / 100)
        p.edit().putInt(IMIT_FIT, ema).putInt(IMIT_N, n + 1).apply()
        return ema
    }

    /** The running imitation-fit EMA (0..100), or -1 if no demonstration has been scored yet. */
    fun imitationFit(c: Context): Int = prefs(c).getInt(IMIT_FIT, -1)

    /** Count of demonstrations scored (for the "over N demos" read-out). */
    fun imitationFitCount(c: Context): Int = prefs(c).getInt(IMIT_N, 0)

    // STARTUP CALIBRATION: the operating posture (an operational-state seed) composed at calibration and the
    // model fingerprint it was made for. Keyed to the fingerprint so a model swap invalidates it (like the
    // distilled-operators store), and the orchestrator seeds the session-σ with it so the first task boots
    // calibrated. On-device only.
    private const val CALIB_POSTURE = "calib_posture"
    private const val CALIB_FP = "calib_fp"

    fun setCalibration(c: Context, fingerprint: String, posture: String) {
        prefs(c).edit().putString(CALIB_POSTURE, posture.take(400)).putString(CALIB_FP, fingerprint).apply()
    }

    /** The calibration posture for the active model, or "" if none / the model changed since calibration. */
    fun calibrationPosture(c: Context, fingerprint: String): String {
        if (prefs(c).getString(CALIB_FP, "") != fingerprint) return ""
        return prefs(c).getString(CALIB_POSTURE, "") ?: ""
    }

    /** True when calibration is stale for this model (never calibrated, or the model was swapped since). */
    fun needsCalibration(c: Context, fingerprint: String): Boolean =
        prefs(c).getString(CALIB_FP, "") != fingerprint

    /** Normalized form for near-duplicate detection (the owner: "lots of duplicates"): case,
     *  punctuation and whitespace runs don't make two copies of the same lesson different. */
    private fun normMem(s: String): String =
        s.lowercase().replace(Regex("[^a-z0-9 ]"), " ").replace(Regex("\\s+"), " ").trim()

    // --- facts (key -> value) --------------------------------------------------

    @Synchronized
    fun setFact(c: Context, key: String, value: String) {
        val k = key.trim().lowercase()
        if (k.isBlank() || value.isBlank()) return
        val o = facts(c).put(k, value.trim())
        prefs(c).edit().putString(FACTS, o.toString()).apply()
    }

    @Synchronized
    fun getFact(c: Context, key: String): String? =
        facts(c).optString(key.trim().lowercase(), "").ifBlank { null }

    @Synchronized
    fun removeFact(c: Context, key: String) {
        val o = facts(c); o.remove(key.trim().lowercase())
        prefs(c).edit().putString(FACTS, o.toString()).apply()
    }

    @Synchronized
    fun factsList(c: Context): List<Pair<String, String>> {
        val o = facts(c)
        return o.keys().asSequence().map { it to o.optString(it) }.toList()
    }

    private fun facts(c: Context): JSONObject =
        try { JSONObject(prefs(c).getString(FACTS, "{}")!!) } catch (_: Exception) { JSONObject() }

    // --- lessons (capped list) -------------------------------------------------

    @Synchronized
    fun addLesson(c: Context, lesson: String) {
        AgentLog.log("mem", "lesson: \"${lesson.trim().take(70)}\"")
        val t = lesson.trim().take(MAX_LESSON_LEN)
        if (t.length < 4) return
        val arr = lessonsArr(c)
        // De-dupe NORMALIZED (the owner: exact-match dedupe let trivially-reworded duplicates
        // pile up): same normalized text, or one lesson containing the other, is one lesson -
        // keep the longer/newer phrasing.
        val n = normMem(t)
        val out = JSONArray()
        for (i in 0 until arr.length()) {
            val old = arr.optString(i); val no = normMem(old)
            if (no == n || n.contains(no)) continue          // superseded by the new phrasing
            if (no.contains(n)) return                        // an existing lesson already covers it
            out.put(old)
        }
        out.put(t)
        // Eviction skips FLASHBULB (⚡) lessons - one-shot high-salience memories (owner corrections,
        // near-disasters) encode permanently, like their human counterpart; ordinary lessons rotate.
        while (out.length() > MAX_LESSONS) {
            var evicted = false
            for (i in 0 until out.length()) {
                if (!out.optString(i).startsWith("⚡")) { out.remove(i); evicted = true; break }
            }
            if (!evicted) break   // all flashbulb - cap suspended rather than forget one
        }
        prefs(c).edit().putString(LESSONS, out.toString()).apply()
    }

    /** FLASHBULB memory (the owner's human-memory taxonomy): a charged, one-shot event - an owner
     *  correction, a §3 near-miss, a task-destroying mistake - encoded ONCE with permanent priority:
     *  never evicted, ranked first when relevant. No re-earning; the event itself is the proof. */
    fun addFlashbulb(c: Context, text: String) = addLesson(c, "⚡ " + text.trim().removePrefix("⚡").trim())

    @Synchronized
    fun lessons(c: Context): List<String> {
        val arr = lessonsArr(c)
        return (0 until arr.length()).map { arr.optString(it) }
    }

    /** Remove a single learned lesson (so the owner can trim a bad/stale one). */
    @Synchronized
    fun removeLesson(c: Context, lesson: String) {
        val arr = lessonsArr(c)
        val out = JSONArray()
        for (i in 0 until arr.length()) {
            val v = arr.optString(i)
            if (!v.equals(lesson, ignoreCase = true)) out.put(v)
        }
        prefs(c).edit().putString(LESSONS, out.toString()).apply()
    }

    /** General lessons/concepts pulled by RELEVANCE to the current goal (not just the last-N), so
     *  broadly-useful knowledge surfaces exactly when it applies. This is the "general memory
     *  alongside the specific ones, retrieved when needed" the owner asked for: specific navigation
     *  lives in observations (keyed by app), while these are app-agnostic concepts ranked by how
     *  well they match the goal, falling back to the most recent few when nothing matches. */
    @Synchronized
    fun lessonsFor(c: Context, goal: String, max: Int = 6): List<String> {
        val all = lessons(c)
        if (all.isEmpty()) return emptyList()
        val goalWords = keywordsOf(goal)
        if (goalWords.isEmpty()) return all.takeLast(max)
        val ranked = all.mapIndexed { i, t -> Triple(t, goalWords.count { it in keywordsOf(t) }, i) }
            // Relevant FLASHBULB (⚡) lessons outrank everything (permanent salience); then relevance, then recency.
            .sortedWith(compareByDescending<Triple<String, Int, Int>> { it.first.startsWith("⚡") && it.second > 0 }
                .thenByDescending { it.second }.thenByDescending { it.third })
        val matched = ranked.filter { it.second > 0 }.map { it.first }
        return (if (matched.isNotEmpty()) matched else all.takeLast(max)).take(max)
    }

    /** Relevance-pulled general lessons as a planner block (empty if none). */
    @Synchronized
    fun lessonsBlockFor(c: Context, goal: String, max: Int = 6): String {
        val ls = lessonsFor(c, goal, max)
        return if (ls.isEmpty()) "" else "GENERAL LESSONS THAT MAY APPLY:\n" + ls.joinToString("\n") { "- $it" }
    }

    /** STUCK-RECOVERY RETRIEVAL ("try a learned principle when stuck"): pull the ONE stored lesson
     *  most similar to the CURRENT situation - objective AND what's actually on screen, not just the
     *  goal - to offer as a CANDIDATE when the loop is spinning. Matching on the screen text is what
     *  makes it "by similarity to the real situation": the same objective can be stuck on different
     *  screens that each need a different principle. Returns null unless a lesson clears a real bar
     *  (>=2 shared keywords) - we'd rather say nothing than inject noise that pulls a healthy run off
     *  track. Caller decides whether to surface it; this never forces an action. */
    @Synchronized
    fun principleForStuck(c: Context, objective: String, screen: String): String? {
        val all = lessons(c)
        if (all.isEmpty()) return null
        val want = keywordsOf(objective) + keywordsOf(screen.take(1200))
        if (want.isEmpty()) return null
        val best = all
            .map { lesson -> val lk = keywordsOf(lesson); lesson to want.count { it in lk } }
            .filter { it.second >= 2 }
            .maxByOrNull { it.second } ?: return null
        return best.first.take(160)
    }

    // --- logins (credentials the agent created; NEVER injected into the prompt) ----

    data class Login(val service: String, val username: String, val secret: String, val time: Long)

    @Synchronized
    fun addLogin(c: Context, service: String, username: String, secret: String) {
        if (service.isBlank()) return
        val arr = loginsArr(c)
        arr.put(JSONObject()
            .put("service", service.trim())
            .put("user", username.trim())
            .put("secret", secret.trim())
            .put("time", System.currentTimeMillis()))
        while (arr.length() > MAX_LOGINS) arr.remove(0)
        prefs(c).edit().putString(LOGINS, arr.toString()).apply()
    }

    @Synchronized
    fun logins(c: Context): List<Login> {
        val arr = loginsArr(c)
        return (0 until arr.length()).mapNotNull {
            // optJSONObject (not the throwing getJSONObject): a non-object element in the LOGINS array must not
            // throw an uncaught JSONException — skip it, matching the null-safe reads used everywhere else here.
            val o = arr.optJSONObject(it) ?: return@mapNotNull null
            Login(o.optString("service"), o.optString("user"), o.optString("secret"), o.optLong("time"))
        }.asReversed()
    }

    private fun loginsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(LOGINS, "[]")) } catch (_: Exception) { JSONArray() }

    /** Delete one stored login (matched on service + username + time), so the owner can prune
     *  credentials the agent created. */
    @Synchronized
    fun removeLogin(c: Context, service: String, username: String, time: Long) {
        val arr = loginsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val match = o.optString("service") == service && o.optString("user") == username && o.optLong("time") == time
            if (!match) out.put(o)
        }
        prefs(c).edit().putString(LOGINS, out.toString()).apply()
    }

    /** Update the secret of one stored login (matched as in [removeLogin]). */
    @Synchronized
    fun updateLoginSecret(c: Context, service: String, username: String, time: Long, secret: String) {
        val arr = loginsArr(c)
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("service") == service && o.optString("user") == username && o.optLong("time") == time) {
                o.put("secret", secret.trim())
            }
        }
        prefs(c).edit().putString(LOGINS, arr.toString()).apply()
    }

    // --- per-app send recipes (which Send strategy worked; executor-internal) ------

    @Synchronized
    fun recordSendRecipe(c: Context, pkg: String, strategy: Int) {
        if (pkg.isBlank() || strategy < 0) return
        val o = sendsObj(c).put(pkg, strategy)
        prefs(c).edit().putString(SENDS, o.toString()).apply()
    }

    @Synchronized
    fun getSendRecipe(c: Context, pkg: String): Int =
        if (pkg.isBlank()) -1 else sendsObj(c).optInt(pkg, -1)

    /** All learned per-app send shortcuts (package -> strategy index), for the memory auditor. */
    @Synchronized
    fun sendRecipes(c: Context): List<Pair<String, Int>> {
        val o = sendsObj(c)
        return o.keys().asSequence().map { it to o.optInt(it, -1) }.toList()
    }

    @Synchronized
    fun removeSendRecipe(c: Context, pkg: String) {
        val o = sendsObj(c); o.remove(pkg)
        prefs(c).edit().putString(SENDS, o.toString()).apply()
    }

    private fun sendsObj(c: Context): JSONObject =
        try { JSONObject(prefs(c).getString(SENDS, "{}")!!) } catch (_: Exception) { JSONObject() }

    // --- structural SEND SKILL: the EXACT field + send control per app (not just a strategy index) -
    // The high-priority "persistent send skill" from the backlog. Learned only once a send is
    // CONFIRMED to have landed, and reused verbatim so a repeat send in a known app clicks the precise
    // Send button instead of re-deriving it through the heuristic ladder (which could wander onto the
    // mic). Keyed (like recipes) by package + screen size, so a fold/unfold gets its own entry.

    /** A learned exact send control: the text field's id + the Send button (by id and/or desc). */
    data class SendSkill(val fieldId: String, val sendId: String, val sendDesc: String, val needsExpand: Boolean)

    @Synchronized
    fun recordSendSkill(c: Context, key: String, fieldId: String, sendId: String, sendDesc: String, needsExpand: Boolean) {
        if (key.isBlank() || (sendId.isBlank() && sendDesc.isBlank())) return
        // NEVER persist a voice/mic control as "send" - learning the mic was the documented send bug.
        val low = "$sendId $sendDesc".lowercase()
        if (low.contains("voice") || low.contains("mic") || low.contains("wave")) return
        val o = sendSkillsObj(c).put(key, JSONObject()
            .put("field", fieldId).put("send", sendId).put("desc", sendDesc).put("expand", needsExpand))
        prefs(c).edit().putString(SEND_SKILLS, o.toString()).apply()
    }

    @Synchronized
    fun getSendSkill(c: Context, key: String): SendSkill? {
        val o = sendSkillsObj(c).optJSONObject(key) ?: return null
        return SendSkill(o.optString("field"), o.optString("send"), o.optString("desc"), o.optBoolean("expand"))
    }

    @Synchronized
    fun removeSendSkill(c: Context, key: String) {
        val o = sendSkillsObj(c); o.remove(key)
        prefs(c).edit().putString(SEND_SKILLS, o.toString()).apply()
    }

    private fun sendSkillsObj(c: Context): JSONObject =
        try { JSONObject(prefs(c).getString(SEND_SKILLS, "{}")!!) } catch (_: Exception) { JSONObject() }

    // --- skills (taught procedures the agent can follow itself) ------------------
    //
    // A skill is a GENERALIZED how-to the owner taught the agent - either by describing it
    // ("Train me: how to send a message in Gemini") or by demonstrating it once. We store the
    // model's generalized step list (labels, not coordinates), not a literal tap replay, so the
    // agent learns the METHOD and can adapt it next time. The best-matching skill is injected
    // into the planner for a new task.

    // [raw] is the literal demonstration/source it was learned from (the recorded taps, or the
    // owner's words), kept ALONGSIDE the generalized [steps] so the owner can see exactly what it
    // learned from what it recorded.
    data class Skill(val name: String, val app: String, val steps: String, val source: String, val time: Long, val raw: String = "", val pinned: Boolean = false, val conf: Int = 0)

    @Synchronized
    fun addSkill(c: Context, name: String, app: String, steps: String, source: String, raw: String = "") {
        val n = name.trim().take(80)
        // #6 PARAMETERIZE: a "completed" playbook is a literal replay of one run's exact values (it
        // "typed \"hi mom\""), which would have the agent re-type stale content next time. Turn that
        // content into fill-in slots so the playbook becomes a reusable TEMPLATE. ONLY for playbooks -
        // owner-described/taught skills keep their literal words (the content IS the instruction), and
        // demonstrations are already generalized by the model. The original is preserved in `raw`.
        val s = (if (source == "completed") templatize(steps) else steps).trim().take(MAX_SKILL_LEN)
        if (n.isBlank() || s.length < 4) return
        // Owner-taught skills (shown/described) are pinned the moment they're created - never auto-drop
        // a skill the owner DELIBERATELY taught.
        val ownerTaught = source.lowercase() in setOf("shown", "described", "taught", "demonstrated")
        val arr = skillsArr(c)
        // Replace any existing skill with the same name (newest teaching wins). Preserve the old raw
        // source, the pinned flag, and the confirmation count across the update.
        val out = JSONArray(); var priorRaw = ""; var priorPinned = false; var priorConf = 0
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("name").equals(n, ignoreCase = true)) {
                priorRaw = o.optString("raw"); priorPinned = o.optBoolean("pinned"); priorConf = o.optInt("conf", 0)
            } else out.put(o)
        }
        // PLASTICITY / STABILITY: each re-save of the same skill (it succeeded again / was re-taught) is
        // a CONFIRMATION. A skill becomes PINNED - a stable core the cap can never evict - once it's
        // owner-taught, already pinned, or confirmed enough times. Everything else is a plastic, LRU-
        // evictable scratch layer. So learning new things never costs the agent its proven core.
        val conf = priorConf + 1
        val pinnedNow = ownerTaught || priorPinned || conf >= SKILL_PROTECT_AT
        out.put(JSONObject()
            .put("name", n).put("app", app.trim().take(40))
            .put("steps", s).put("source", source).put("time", System.currentTimeMillis())
            .put("conf", conf).put("pinned", pinnedNow)
            .put("raw", raw.trim().ifBlank { priorRaw }.take(MAX_SKILL_LEN)))
        // Evict the OLDEST UNPINNED skill to honor the cap, keeping the pinned core. Only if EVERY
        // skill is pinned do we drop the oldest outright (the cap is a hard ceiling).
        while (out.length() > MAX_SKILLS) {
            val drop = (0 until out.length()).firstOrNull { out.optJSONObject(it)?.optBoolean("pinned") != true } ?: 0
            out.remove(drop)
        }
        prefs(c).edit().putString(SKILLS, out.toString()).apply()
    }

    /** Owner pin/unpin from the Skills view: a pinned skill is never auto-evicted by the cap. */
    @Synchronized
    fun setSkillPinned(c: Context, name: String, on: Boolean) {
        val arr = skillsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("name").equals(name, ignoreCase = true)) o.put("pinned", on)
            out.put(o)
        }
        prefs(c).edit().putString(SKILLS, out.toString()).apply()
    }

    @Synchronized
    fun skills(c: Context): List<Skill> {
        val arr = skillsArr(c)
        return (0 until arr.length()).mapNotNull {
            val o = arr.optJSONObject(it) ?: return@mapNotNull null
            Skill(o.optString("name"), o.optString("app"), o.optString("steps"),
                o.optString("source"), o.optLong("time"), o.optString("raw"),
                o.optBoolean("pinned"), o.optInt("conf", 0))
        }.asReversed()
    }

    @Synchronized
    fun removeSkill(c: Context, name: String) {
        val arr = skillsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("name").equals(name, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(SKILLS, out.toString()).apply()
    }

    /** Parse a model "SKILL:/APP:/STEPS:" reply into a stored skill. Returns the name, or null
     *  if the reply had no usable steps. [fallbackName] is used when the model omits SKILL:. */
    @Synchronized
    fun addSkillFromModel(c: Context, modelText: String, source: String, fallbackName: String, raw: String = ""): String? {
        val lines = modelText.lines()
        var name = ""; var app = ""
        val stepLines = mutableListOf<String>()
        var inSteps = false
        for (raw in lines) {
            val line = raw.trim()
            when {
                line.startsWith("SKILL:", true) -> name = line.substringAfter(':').trim()
                line.startsWith("APP:", true) -> app = line.substringAfter(':').trim()
                line.startsWith("STEPS:", true) -> { inSteps = true; line.substringAfter(':').trim().let { if (it.isNotBlank()) stepLines.add(it) } }
                inSteps && line.isNotBlank() -> stepLines.add(line)
            }
        }
        // Fallback if the model ignored the format: treat any numbered lines as the steps.
        if (stepLines.isEmpty()) lines.map { it.trim() }.filter { it.matches(Regex("^\\d+[.)].*")) }.let { stepLines.addAll(it) }
        if (stepLines.isEmpty()) return null
        if (name.isBlank()) name = fallbackName.trim().take(80).ifBlank { "untitled skill" }
        if (app.equals("any", true)) app = ""
        addSkill(c, name, app, stepLines.joinToString("\n"), source, raw)
        return name
    }

    private fun skillsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(SKILLS, "[]")) } catch (_: Exception) { JSONArray() }

    /** The skills most relevant to an objective (token overlap on name/app), best first. */
    @Synchronized
    fun skillsForObjective(c: Context, objective: String): List<Skill> {
        val want = tokens(objective)
        if (want.isEmpty()) return emptyList()
        return skills(c).map { it to scoreOverlap(want, tokens(it.name + " " + it.app)) }
            .filter { it.second > 0 }
            .sortedByDescending { it.second }
            .take(2).map { it.first }
    }

    /** Planner block naming the procedure(s) that apply to this task (empty if none). A playbook
     *  auto-saved from a SUCCESSFUL run (source="completed") is PROVEN - we pin it ("this exact
     *  sequence finished the task before"); an owner-taught one is framed as instruction. Both still
     *  say "adapt to the live screen", so pinning never forces a blind, screen-blind replay. */
    @Synchronized
    fun skillsBlockFor(c: Context, objective: String): String {
        val s = skillsForObjective(c, objective)
        if (s.isEmpty()) return ""
        val sb = StringBuilder()
        s.forEach { sk ->
            // REFERENCE, not gospel (the owner's rule: "agent should reference them, not blindly
            // accept"): the playbook is the MAP, the live screen is the TERRITORY - each step gets
            // verified against what's actually on screen before it's used, and reality always wins.
            val header = if (sk.source == "completed")
                "✓ PROVEN ROUTE (a REFERENCE - this sequence completed the task before): check EACH step against the live screen before doing it; follow where it matches, adapt where it doesn't - the screen is the truth, this is just the map:"
            else "THE OWNER TAUGHT YOU HOW TO DO THIS - follow the intent; verify each step against the live screen:"
            sb.append(header).append("\n[").append(sk.name).append("]\n").append(sk.steps).append('\n')
            // #6: a templated playbook carries {text}/{number} slots - tell the model to FILL them from
            // THIS task, not to type the literal placeholder (so a generalized playbook actually generalizes).
            if (sk.steps.contains("{text}") || sk.steps.contains("{number}"))
                sb.append("(fill {text}/{number} with THIS task's actual message/value - never type the braces.)\n")
        }
        return sb.toString().trim()
    }

    /** #6: replace clearly-variable content in a playbook with fill-in slots, so it's a reusable
     *  template not a one-task replay. Conservative on purpose - only a quoted run (a typed message) and
     *  a long digit run (a phone number) become slots; navigation words are left exactly as they are. */
    private fun templatize(steps: String): String =
        steps.replace(Regex("\"[^\"]{1,200}\""), "{text}")
             .replace(Regex("\\b\\d{7,}\\b"), "{number}")

    private fun tokens(s: String): Set<String> =
        Regex("[a-z0-9]+").findAll(s.lowercase()).map { it.value }.filter { it.length >= 3 }.toSet()

    private fun scoreOverlap(a: Set<String>, b: Set<String>): Int = a.count { it in b }

    // --- "things I can't do yet" (failed tasks the owner can teach) --------------

    @Synchronized
    fun addUnknownAction(c: Context, what: String) {
        val t = what.trim().take(140)
        if (t.length < 4) return
        val arr = unknownArr(c)
        for (i in 0 until arr.length())
            if (arr.optJSONObject(i)?.optString("what").equals(t, ignoreCase = true)) return
        arr.put(JSONObject().put("what", t).put("time", System.currentTimeMillis()))
        while (arr.length() > MAX_UNKNOWN) arr.remove(0)
        prefs(c).edit().putString(UNKNOWN, arr.toString()).apply()
    }

    @Synchronized
    fun unknownActions(c: Context): List<String> {
        val arr = unknownArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it)?.optString("what") }.asReversed()
    }

    @Synchronized
    fun removeUnknownAction(c: Context, what: String) {
        val arr = unknownArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("what").equals(what, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(UNKNOWN, out.toString()).apply()
    }

    private fun unknownArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(UNKNOWN, "[]")) } catch (_: Exception) { JSONArray() }

    // --- device scan (the apps installed on this phone, a navigation aid) --------

    @Synchronized
    fun setDeviceApps(c: Context, apps: List<String>) {
        // Keep MORE of what's installed (the owner asked the agent to remember as much useful info
        // as it can); the injected line is still capped so the prompt stays lean.
        val arr = JSONArray(); apps.distinct().take(220).forEach { arr.put(it) }
        prefs(c).edit().putString(APPS, arr.toString()).apply()
    }

    @Synchronized
    fun deviceApps(c: Context): List<String> {
        val arr = try { JSONArray(prefs(c).getString(APPS, "[]")) } catch (_: Exception) { JSONArray() }
        return (0 until arr.length()).map { arr.optString(it) }
    }

    /** Compact one-line hint of what's installed, for the planner (empty if not scanned). */
    @Synchronized
    fun deviceAppsLine(c: Context): String {
        val a = deviceApps(c)
        if (a.isEmpty()) return ""
        return "Apps installed on this phone (open these by name): " + a.joinToString(", ").take(900)
    }

    // --- device profile (durable phone facts: model, OS, screen, DEFAULT apps) ----------
    // A compact, stable line the agent should always know so it routes correctly (e.g. uses THIS
    // phone's real default browser/texting app instead of guessing). Re-derived on each scan.

    @Synchronized
    fun setDeviceProfile(c: Context, text: String) {
        val t = text.trim().take(500)
        prefs(c).edit().putString(PROFILE, t).apply()
    }

    @Synchronized
    fun deviceProfile(c: Context): String = prefs(c).getString(PROFILE, "").orEmpty()

    /** The device-profile line for prompts (empty if not scanned yet). */
    @Synchronized
    fun deviceProfileLine(c: Context): String {
        val p = deviceProfile(c)
        return if (p.isBlank()) "" else "This device: $p"
    }

    // --- persistent IDENTITY (the agent's continuous self) -----------------------
    // Created ONCE on first use and surfaced into the agent's context every task, so the agent is the
    // SAME entity across the owner's whole experience - through app restarts, sleep, and emergency
    // stop (none of which touch it; SharedPreferences persists it). Only a full memory wipe (`clear`)
    // resets it, which reincarnates the agent with a fresh birth date. NOT per-session, NOT per-task.

    @Synchronized
    fun identity(c: Context): JSONObject {
        val o = try { JSONObject(prefs(c).getString(IDENTITY, "{}")!!) } catch (_: Exception) { JSONObject() }
        if (!o.has("born")) {   // first ever run on this install (or first after a wipe): give birth
            o.put("name", "Agent").put("born", System.currentTimeMillis()).put("tasks", 0)
            prefs(c).edit().putString(IDENTITY, o.toString()).apply()
        }
        return o
    }

    fun agentName(c: Context): String = identity(c).optString("name", "Agent").ifBlank { "Agent" }

    /** Count one finished task toward the agent's accumulated experience (a continuity signal). */
    @Synchronized
    fun bumpTasksDone(c: Context) {
        val o = identity(c)
        o.put("tasks", o.optInt("tasks", 0) + 1)
        prefs(c).edit().putString(IDENTITY, o.toString()).apply()
    }

    /** A1 ACCEPTANCE ORACLE — record one finished task's AGENT-DRIVEN outcome, attributed to the operators the
     *  flywheel credited this task and the flag CONFIG it ran under. Owner-STOPPED tasks go to a separate
     *  `interrupted` tally (they're not a clean signal), so they never pollute the attribution. Telemetry only
     *  (§2/§12): nothing here enters a prompt, tunes a constant, or selects an action - it's the fitness signal
     *  the owner reads and A5's weight keep-gate trusts. Best-effort + fully guarded (a ledger write must never
     *  disturb the loop). */
    @Synchronized
    fun recordTaskOutcome(c: Context, success: Boolean, ownerStopped: Boolean, operators: List<String>, flagSig: String) {
        try {
            val root = JSONObject(prefs(c).getString(ORACLE, "{}") ?: "{}")
            if (ownerStopped) {
                root.put("interrupted", root.optInt("interrupted", 0) + 1)
                prefs(c).edit().putString(ORACLE, root.toString()).apply(); return
            }
            fun bump(obj: JSONObject, key: String, ok: Boolean) {
                val cell = obj.optJSONObject(key) ?: JSONObject().also { obj.put(key, it) }
                cell.put("n", cell.optInt("n", 0) + 1); if (ok) cell.put("s", cell.optInt("s", 0) + 1)
            }
            val clean = root.optJSONObject("clean") ?: JSONObject().also { root.put("clean", it) }
            clean.put("n", clean.optInt("n", 0) + 1); if (success) clean.put("s", clean.optInt("s", 0) + 1)
            val ops = root.optJSONObject("ops") ?: JSONObject().also { root.put("ops", it) }
            operators.map { it.uppercase() }.filter { it.isNotBlank() && it != "DIRECT" }.distinct()
                .forEach { bump(ops, it, success) }
            val flags = root.optJSONObject("flags") ?: JSONObject().also { root.put("flags", it) }
            if (flagSig.isNotBlank()) bump(flags, flagSig.take(40), success)
            // Cap distinct flag-configs: past the cap, evict the lowest-n row (the least-informative sample).
            if (flags.length() > MAX_ORACLE_FLAGS) {
                var worst: String? = null; var worstN = Int.MAX_VALUE
                flags.keys().forEach { k -> val n = flags.optJSONObject(k)?.optInt("n", 0) ?: 0; if (n < worstN) { worstN = n; worst = k } }
                worst?.let { flags.remove(it) }
            }
            prefs(c).edit().putString(ORACLE, root.toString()).apply()
        } catch (_: Throwable) {}
    }

    /** A1: a compact one-line readout of the attributed success rate — the clean agent-driven rate, the top
     *  operators by sample with their hit-rate, and the CURRENT flag-config's rate — so the owner can SEE what's
     *  actually working, and A5 can read a per-operator/per-config fitness. "" until there's clean history. */
    @Synchronized
    fun oracleReadout(c: Context, currentFlagSig: String = ""): String {
        return try {
            val root = JSONObject(prefs(c).getString(ORACLE, "{}") ?: "{}")
            val clean = root.optJSONObject("clean") ?: return ""
            val n = clean.optInt("n", 0); if (n == 0) return ""
            val s = clean.optInt("s", 0); val pct = s * 100 / n
            val interrupted = root.optInt("interrupted", 0)
            val ops = root.optJSONObject("ops")
            val opStr = if (ops == null) "" else ops.keys().asSequence()
                .map { it to (ops.optJSONObject(it)!!) }
                .sortedByDescending { it.second.optInt("n", 0) }.take(3)
                .joinToString(",") { "${it.first} ${it.second.optInt("s",0)}/${it.second.optInt("n",0)}" }
            val cfg = root.optJSONObject("flags")?.optJSONObject(currentFlagSig.take(40))
            val cfgStr = if (cfg == null) "" else " · cfg[$currentFlagSig] ${cfg.optInt("s",0)}/${cfg.optInt("n",0)}"
            "agent-driven $s/$n=$pct% clean" + (if (interrupted > 0) " ($interrupted interrupted)" else "") +
                (if (opStr.isNotBlank()) " · ops: $opStr" else "") + cfgStr
        } catch (_: Throwable) { "" }
    }

    /** #10 RESUMABLE TASKS: persist the live task's state each step so an OS kill (OOM/black wallpaper)
     *  or a force-stop doesn't lose it. A clean finish() CLEARS it; if the process is reaped mid-task the
     *  record survives and the next launch can offer to resume. Stores the objective + the condensed
     *  progress note (what's already been done) + step count + time. */
    @Synchronized
    fun saveCheckpoint(c: Context, objective: String, progress: String, steps: Int) {
        if (objective.isBlank()) return
        val o = JSONObject().put("objective", objective.take(400)).put("progress", progress.take(600))
            .put("steps", steps).put("time", System.currentTimeMillis())
        prefs(c).edit().putString(CHECKPOINT, o.toString()).apply()
    }

    @Synchronized
    fun clearCheckpoint(c: Context) { prefs(c).edit().remove(CHECKPOINT).apply() }

    /** The pending interrupted task, if one was left within the last 6 hours (older = stale, ignored):
     *  (objective, progress-note, steps). Null when there's nothing worth resuming. */
    @Synchronized
    fun getCheckpoint(c: Context): Triple<String, String, Int>? {
        val s = prefs(c).getString(CHECKPOINT, null) ?: return null
        val o = try { JSONObject(s) } catch (_: Exception) { return null }
        if (System.currentTimeMillis() - o.optLong("time", 0) > 6 * 60 * 60 * 1000L) return null
        val obj = o.optString("objective"); if (obj.isBlank()) return null
        return Triple(obj, o.optString("progress"), o.optInt("steps", 0))
    }

    /** One line for the agent's context: who it is + that it persists across sessions (continuity),
     *  so it reasons as the SAME entity that ran before, not a blank slate each launch. */
    @Synchronized
    fun identityLine(c: Context): String {
        val o = identity(c)
        val name = o.optString("name", "Agent").ifBlank { "Agent" }
        val days = ((System.currentTimeMillis() - o.optLong("born", System.currentTimeMillis())) / 86_400_000L).toInt()
        val since = when { days <= 0 -> "today"; days == 1 -> "1 day ago"; else -> "$days days ago" }
        val tasks = o.optInt("tasks", 0)
        return "YOU: $name, this phone's OWN persistent agent - the SAME agent across every session. " +
            "Your memory carries over through restarts, sleep, and stop; you are NOT a blank slate. " +
            "You came online $since" + (if (tasks > 0) " and have completed $tasks tasks for your owner since." else ".")
    }

    // --- VALUES: the agent's character (owner-set), the TOP tier of memory ---------------------
    // Agency at its core is DESIRE: one acts to fulfill what one VALUES. Facts are knowledge,
    // lessons are know-how, skills are procedures - VALUES are who the agent IS, the priors that
    // color every decision. OWNER-SET only (never learned - character isn't scraped off a screen),
    // injected as a motivational orientation block so the model pursues the owner's goal in a way that
    // honors them and VOICES a conflict rather than silently acting against a value. The "desire
    // mechanism" is NOT deterministic action-selection (that would grab the wheel, CLAUDE §2) - it
    // is this: values in the model's context + intensity as desire-STRENGTH + the standing
    // instruction to prefer the value-aligned path and voice a conflict. The model does the wanting;
    // we only give it something to want. TWO things stay SOVEREIGN over any value: an explicit owner
    // command, and the executor's hard safety gates (§3) - both enforced elsewhere and supreme.

    @Synchronized
    fun addValue(c: Context, text: String, intensity: Int = 2) {
        val t = text.trim().take(MAX_VALUE_LEN)
        if (t.length < 3) return
        val w = intensity.coerceIn(1, 3)
        val arr = valuesArr(c)
        val n = normMem(t)
        val out = JSONArray()
        // Replace a near-duplicate (same normalized text) so re-adding just updates the intensity.
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (normMem(o.optString("t")) != n) out.put(o)
        }
        out.put(JSONObject().put("t", t).put("w", w).put("time", System.currentTimeMillis()))
        while (out.length() > MAX_VALUES) out.remove(0)
        prefs(c).edit().putString(VALUES, out.toString()).apply()
    }

    @Synchronized
    fun values(c: Context): List<String> {
        val arr = valuesArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it)?.optString("t") }
    }

    /** (text, intensity 1..3) newest first - for the values UI. */
    @Synchronized
    fun valuesDetailed(c: Context): List<Pair<String, Int>> {
        val arr = valuesArr(c)
        return (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .map { it.optString("t") to it.optInt("w", 2) }
    }

    @Synchronized
    fun removeValue(c: Context, text: String) {
        val arr = valuesArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("t").equals(text, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(VALUES, out.toString()).apply()
    }

    private fun valuesArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(VALUES, "[]")) } catch (_: Exception) { JSONArray() }

    /** The motivational orientation block: the agent's values framed as what it WANTS to honor - the
     *  desire mechanism (the model does the wanting; this gives it something to want). "" if none.
     *  Strongest desire first; intensity 3 marked ★. Injected in the planner (shapes the whole
     *  approach) and the action loop (colors each choice); the loop DROPS it on dense screens like
     *  the other optional blocks, because an always-present identity clause once overflowed the 4096
     *  budget and triggered the black-wallpaper OOM (the 98e673a lesson). */
    @Synchronized
    fun valuesBlock(c: Context, max: Int = 5): String {
        val arr = valuesArr(c)
        if (arr.length() == 0) return ""
        val items = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .sortedByDescending { it.optInt("w", 2) }.take(max)
        if (items.isEmpty()) return ""
        val body = items.joinToString("\n") {
            (if (it.optInt("w", 2) >= 3) "★ " else "• ") + it.optString("t")
        }
        return "YOUR VALUES - who you are, and what you WANT to honor in HOW you act (★ = held most " +
            "deeply). Let them guide which choices you prefer and how you pursue the goal; pursue it " +
            "in the way that best honors them:\n$body\n" +
            "Use these values as context while pursuing the objective."
    }

    // --- OWNER OPERATORS: the owner's own reasoning moves that JOIN the operator menu ----------
    // Mirror of VALUES, but for the operator layer. Where values are WHO the agent is (priors that
    // color every decision), owner operators are HOW it may think (reusable reasoning "moves"). Both
    // are the owner's DELIBERATE input the MODEL reasons WITH - it SELECTS the move that fits the
    // screen (§2), exactly as it weighs values; code never fires one. The one hard rule: an owner
    // operator is a CLAUSE, never a forced action or a veto - structural, because the only path from
    // a stored move into a prompt is ReasoningOperators.inject()'s "HOW TO THINK NOW:" header (there
    // is NO path from an authored operator to an executed action; do not add one). Each row is
    // {n: NAME, w: when-to-use, d: how-to-think}, mapped to the SAME Operator shape parseGenerated
    // produces so it drops straight into the runtime-list plumbing.

    @Synchronized
    fun addOwnerOperator(c: Context, name: String, whenTo: String, doThis: String) {
        // Sanitize the NAME to ONE uppercase word (the operator-name shape parseGenerated makes), so
        // it slots into the menu / whole-word normalize match cleanly; reject a too-short one.
        val n = name.trim().uppercase().replace(Regex("[^A-Z]"), "").take(MAX_OWNER_OP_NAME)
        if (n.length < 3) return
        val d = doThis.trim().take(MAX_OWNER_OP_DO)
        if (d.length < 4) return
        val w = whenTo.trim().take(MAX_OWNER_OP_WHEN)
        // Never shadow a BAKED move or the DIRECT sentinel: a name collision would make the menu
        // ambiguous and let an owner move silently ride on a baked one in normalize's word match.
        val reserved = ReasoningOperators.BAKED.map { it.name.uppercase() }.toSet() + ReasoningOperators.DIRECT
        if (n in reserved) return
        val arr = ownerOpsArr(c)
        val out = JSONArray()
        // Dedup by NAME (replace) so re-adding a move updates its when/do instead of duplicating it.
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("n").equals(n, ignoreCase = true)) out.put(o)
        }
        out.put(JSONObject().put("n", n).put("w", w).put("d", d).put("time", System.currentTimeMillis()))
        while (out.length() > MAX_OWNER_OPS) out.remove(0)   // FIFO cap - keep the menu legible
        prefs(c).edit().putString(OP_OWNER, out.toString()).apply()
        AgentLog.log("op", "owner move saved: $n (${out.length()}/$MAX_OWNER_OPS)")
    }

    @Synchronized
    fun removeOwnerOperator(c: Context, name: String) {
        val arr = ownerOpsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("n").equals(name, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(OP_OWNER, out.toString()).apply()
    }

    /** (name, when, do) newest first - for the owner-operator editor UI. */
    @Synchronized
    fun ownerOperatorsDetailed(c: Context): List<Triple<String, String, String>> {
        val arr = ownerOpsArr(c)
        return (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .map { Triple(it.optString("n"), it.optString("w"), it.optString("d")) }
    }

    /** The owner's moves as runtime Operators - the SAME shape parseGenerated produces (generated=true,
     *  clause "Think NAME: <do>"), so they union straight into the runtime list the model SELECTS from
     *  (ReasoningOperators.menuText / normalize / inject). "" list when the owner has authored none. */
    @Synchronized
    fun ownerOperators(c: Context): List<ReasoningOperators.Operator> {
        val arr = ownerOpsArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.mapNotNull { o ->
            val n = o.optString("n"); val d = o.optString("d")
            if (n.length < 3 || d.length < 4) null
            else ReasoningOperators.Operator(n, o.optString("w"), "Think $n: $d", generated = true)
        }
    }

    private fun ownerOpsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(OP_OWNER, "[]")) } catch (_: Exception) { JSONArray() }

    // --- AGENT OPERATORS (W2): reasoning moves the AGENT authored, kept ONLY if they earn their keep ----
    // The owner's "the agent needs to create his OWN operators" - the marquee item. The math (his operator
    // algebra): the operator set 𝒯 IS the system's leverage ("𝒯 determines the geometry of the entire
    // system"), so growing/refining 𝒯 is the highest-value move - but govern admission by the NOVELTY
    // criterion (novel iff not a dup / trivial composition of prior moves) and SURVIVAL by measured reward
    // (prefer reduction over expansion / Mirror Invariance: keep the minimal set that works). §2: the MODEL
    // authors + selects the clause; code only MEASURES M (OP_CREDIT) and PROMOTES/PRUNES - it never forces
    // or executes a move, and survival is an EXTERNAL signal (the reward), never the model's self-judgment.

    /** NOVELTY guard: [name] is worth minting only if it's not already a baked/owner/agent move, and not
     *  the literal concatenation of two known moves (a trivial composition adds nothing the pair doesn't -
     *  monoid closure; the agent can just SEQUENCE them at runtime). One uppercase word. */
    @Synchronized
    fun isNovelOperator(c: Context, name: String): Boolean {
        val n = name.trim().uppercase().replace(Regex("[^A-Z]"), "")
        if (n.length < 3) return false
        val known = (ReasoningOperators.BAKED.map { it.name.uppercase() } +
            ReasoningOperators.DIRECT +
            ownerOperators(c).map { it.name.uppercase() } +
            agentOperators(c).map { it.name.uppercase() }).toSet()
        if (n in known) return false
        for (a in known) for (b in known) if (a != b && a + b == n) return false  // reject a trivial A+B composition name
        return true
    }

    /** Scan OP_CREDIT across ALL apps for operator [name]: (total evidence n, evidence-weighted avg M).
     *  The survival signal for an agent-authored move (proven positive => promote; turned negative => prune). */
    @Synchronized
    fun operatorNetValue(c: Context, name: String): Pair<Int, Double> {
        val target = name.trim().uppercase(); if (target.isBlank()) return 0 to 0.0
        val root = try { JSONObject(prefs(c).getString(OP_CREDIT, "{}")!!) } catch (_: Exception) { return 0 to 0.0 }
        var totN = 0; var acc = 0.0
        val apps = root.keys()
        while (apps.hasNext()) {
            val o = root.optJSONObject(apps.next())?.optJSONObject(target) ?: continue
            val n = o.optInt("n"); totN += n; acc += o.optDouble("m") * n
        }
        return totN to (if (totN > 0) acc / totN else 0.0)
    }

    /** The PROMOTION gate: [name] proved out in at least one app (chosen >=2 with a positive avg M). */
    @Synchronized
    fun operatorProvedAnywhere(c: Context, name: String): Boolean {
        val target = name.trim().uppercase(); if (target.isBlank()) return false
        val root = try { JSONObject(prefs(c).getString(OP_CREDIT, "{}")!!) } catch (_: Exception) { return false }
        val apps = root.keys()
        while (apps.hasNext()) {
            val o = root.optJSONObject(apps.next())?.optJSONObject(target) ?: continue
            if (o.optInt("n") >= 2 && o.optDouble("m") > 0) return true
        }
        return false
    }

    // OPERATOR EXACTNESS (self-calibrate, legs 2+4 — the owner's "operators are EXACT, not fuzzy hopes"):
    // an operator RESTRICTS generation to an admissible state; it either HELD (the restriction held — the
    // operator-driven action survived verification / made progress) or ESCAPED (the restriction was violated —
    // a kickback fired or the step regressed). Tracked per operator (app-agnostic — exactness is a property of
    // the operator's rule vs the model), so the self-tune loop can promote the proven-AND-exact operators and
    // prune the LEAKY ones. Distinct from OP_CREDIT (which measures HELPED — the M reward); this measures HELD
    // — did the exact restriction bind. §2: a measured signal from the loop, never the model's self-judgment.
    private const val OP_EXACT = "op_exact"          // {OP: {held, tot}}
    private const val MAX_EXACT_KEYS = 60

    @Synchronized
    fun creditOperatorExactness(c: Context, name: String, held: Boolean) {
        val n = name.trim().uppercase(); if (n.isBlank() || n == ReasoningOperators.DIRECT) return
        val root = try { JSONObject(prefs(c).getString(OP_EXACT, "{}")!!) } catch (_: Exception) { JSONObject() }
        val o = root.optJSONObject(n) ?: JSONObject()
        o.put("held", o.optInt("held") + (if (held) 1 else 0)).put("tot", o.optInt("tot") + 1)
        root.put(n, o)
        // FIFO-ish cap: if we blow the key budget, drop the lowest-evidence key so the store stays bounded.
        if (root.length() > MAX_EXACT_KEYS) {
            var minK: String? = null; var minTot = Int.MAX_VALUE
            val it = root.keys(); while (it.hasNext()) { val k = it.next(); val t = root.optJSONObject(k)?.optInt("tot") ?: 0; if (t < minTot) { minTot = t; minK = k } }
            if (minK != null) root.remove(minK)
        }
        prefs(c).edit().putString(OP_EXACT, root.toString()).apply()
    }

    /** (evidence tot, escape rate 0..1) for [name] — how often the operator's restriction was VIOLATED.
     *  (0, 0.0) when there's no evidence yet. A low rate = an EXACT operator; a high rate = a leaky one. */
    @Synchronized
    fun operatorEscapeRate(c: Context, name: String): Pair<Int, Double> {
        val n = name.trim().uppercase(); if (n.isBlank()) return 0 to 0.0
        val o = try { JSONObject(prefs(c).getString(OP_EXACT, "{}")!!).optJSONObject(n) } catch (_: Exception) { null } ?: return 0 to 0.0
        val tot = o.optInt("tot"); if (tot <= 0) return 0 to 0.0
        return tot to ((tot - o.optInt("held")).toDouble() / tot)
    }

    // PER-APP σ CONTROLLER (Batch 3 / the persistent σ-controller): the operating posture that PROVED OUT for an
    // app this session, persisted so OPENING that app next time boots SPECIALIZED — a durable, per-device, per-app
    // learned operational state (fine-tune-without-training, no gradients). Owner-gated by session_sigma; written
    // only on a CLEAN completion so we compound real wins, not stalls. Advisory CONTEXT the model reads (§2); it
    // never selects an action. Capped like the other per-app stores.
    private const val PER_APP_SIGMA = "per_app_sigma"   // {app: {sigma, hits}}
    private const val MAX_SIGMA_APPS = 40
    private const val MAX_SIGMA_LEN = 200

    /** Batch 9 (Weight Forge / §3 seed): the operators that have proven EXACT (enough evidence, low escape rate).
     *  Used as the LEARNING-DERIVED, on-screen-text-FREE seed for the self-evolve/grow weight edits, so a permanent
     *  weight change is steered ONLY by what the agent PROVED — never by anything on screen (the §3 exploit gate:
     *  self-modification must never be triggerable by on-screen/external data). Sorted for a stable seed. */
    @Synchronized
    fun provenExactOperators(c: Context): List<String> {
        val root = try { JSONObject(prefs(c).getString(OP_EXACT, "{}")!!) } catch (_: Exception) { return emptyList() }
        val out = ArrayList<String>()
        val it = root.keys()
        while (it.hasNext()) {
            val k = it.next(); val o = root.optJSONObject(k) ?: continue
            val tot = o.optInt("tot"); val held = o.optInt("held")
            if (tot >= 3 && (tot - held).toDouble() / tot <= 0.25) out.add(k)   // enough evidence, low escape rate
        }
        return out.sorted()
    }

    /** GROUNDED-TRUTH SELF-MOD SEED (owner: "ground weight modification in truth" — the thesis, applied to weights).
     *  A digest of everything the agent has VERIFIED: its proven-exact operators AND the navigation observations that
     *  re-confirmed by REAL repeated success (isProvenObs = hits≥2, miss==0, never falsified, policy-safe). Each is
     *  truth-grounded BY CONSTRUCTION — an entry becomes "proven" only after the action actually WORKED, repeatedly,
     *  which a hostile SCREEN cannot fabricate (displayed text is not proof; only real outcomes are). So a weight
     *  edit seeded from this is rich (the agent's real verified experience, not just operator names) yet cannot be
     *  steered by injected on-screen content — it blocks the cheap display-injection class. (Residual: an
     *  environment-level attacker who manufactures genuinely-true adversarial outcomes over many real interactions —
     *  the same, far higher, bar as poisoning any on-device learning loop; the owner accepts that.) Excludes ALL
     *  raw/unverified perception (the log tail, live screen text, un-proven observations). */
    @Synchronized
    fun groundedLearningDigest(c: Context): String {
        val sb = StringBuilder("ops:").append(provenExactOperators(c).joinToString(","))
        sb.append("|obs:")
        try {
            val arr = obsArr(c)
            var n = 0
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                // ONLY proven-by-real-success, non-falsified observations — never a raw screen dump.
                if (isProvenObs(o) && !o.optBoolean("false")) {
                    sb.append(o.optString("k")).append(':').append(o.optString("t")).append(';')
                    if (++n >= 60) break
                }
            }
        } catch (_: Exception) {}
        return sb.toString().take(4000)
    }

    /** The stored per-app operating posture for [app], or "" if none. */
    @Synchronized
    fun perAppSigma(c: Context, app: String): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        return try { JSONObject(prefs(c).getString(PER_APP_SIGMA, "{}")!!).optJSONObject(a)?.optString("sigma").orEmpty() } catch (_: Exception) { "" }
    }

    /** Persist the posture that proved out for [app] on a clean completion (Batch 3). Keeps the most recent useful
     *  posture, bumps a hit counter, and FIFO-caps by fewest hits so the store stays bounded. */
    @Synchronized
    fun savePerAppSigma(c: Context, app: String, sigma: String) {
        val a = app.trim().lowercase(); val s = sigma.trim().take(MAX_SIGMA_LEN)
        if (a.isBlank() || s.isBlank()) return
        val root = try { JSONObject(prefs(c).getString(PER_APP_SIGMA, "{}")!!) } catch (_: Exception) { JSONObject() }
        val o = root.optJSONObject(a) ?: JSONObject()
        o.put("sigma", s).put("hits", o.optInt("hits") + 1)
        root.put(a, o)
        if (root.length() > MAX_SIGMA_APPS) {
            var minK: String? = null; var minH = Int.MAX_VALUE
            val it = root.keys(); while (it.hasNext()) { val k = it.next(); val h = root.optJSONObject(k)?.optInt("hits") ?: 0; if (h < minH) { minH = h; minK = k } }
            if (minK != null) root.remove(minK)
        }
        prefs(c).edit().putString(PER_APP_SIGMA, root.toString()).apply()
    }

    /** The distillation gate: [name] is PROVEN (positive M in some app) AND EXACT (enough evidence, low escape
     *  rate) — a real, reliable capability worth caching into the weights (owner-approved). */
    @Synchronized
    fun operatorProvenExact(c: Context, name: String): Boolean {
        if (!operatorProvedAnywhere(c, name)) return false
        val (tot, rate) = operatorEscapeRate(c, name)
        return tot >= 3 && rate <= 0.34
    }

    /** Prune-gate helper: [name] is LEAKY — enough evidence and its restriction is violated too often to be a
     *  real capability, so it should be dropped even if its M looks okay (an inexact operator is not a win). */
    @Synchronized
    fun operatorIsLeaky(c: Context, name: String): Boolean {
        val (tot, rate) = operatorEscapeRate(c, name)
        return tot >= 4 && rate >= 0.6
    }

    /** Promote an agent-authored move into the PERSISTENT library - called at task end for a move the agent
     *  authored this task that EARNED its keep (operatorProvedAnywhere). Novelty-checked, deduped, FIFO-capped. */
    @Synchronized
    fun promoteAgentOperator(c: Context, op: ReasoningOperators.Operator) {
        val n = op.name.trim().uppercase().replace(Regex("[^A-Z]"), "").take(MAX_OWNER_OP_NAME)
        if (n.length < 3) return
        val reserved = ReasoningOperators.BAKED.map { it.name.uppercase() }.toSet() + ReasoningOperators.DIRECT +
            ownerOperators(c).map { it.name.uppercase() }
        if (n in reserved) return
        val d = op.clause.removePrefix("Think ${op.name}: ").removePrefix("Think $n: ").trim().take(MAX_OWNER_OP_DO)
        if (d.length < 4) return
        val arr = agentOpsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("n").equals(n, ignoreCase = true)) out.put(o)   // dedup by NAME (replace)
        }
        out.put(JSONObject().put("n", n).put("w", op.whenToUse.take(MAX_OWNER_OP_WHEN)).put("d", d).put("time", System.currentTimeMillis()))
        while (out.length() > MAX_AGENT_OPS) out.remove(0)   // FIFO cap - keep the menu legible
        prefs(c).edit().putString(OP_AGENT, out.toString()).apply()
        AgentLog.log("op", "agent move PROMOTED (proven): $n (${out.length()}/$MAX_AGENT_OPS)")
    }

    /** Prefer-reduction: drop any persisted agent move that TURNED bad (aggregate M<0 with enough evidence),
     *  so the library converges to the minimal set that works. Returns the count pruned. */
    @Synchronized
    fun pruneAgentOperators(c: Context): Int {
        val arr = agentOpsArr(c); if (arr.length() == 0) return 0
        val out = JSONArray(); var pruned = 0
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val name = o.optString("n")
            val (n, m) = operatorNetValue(c, name)
            when {
                n >= 3 && m < 0 -> { pruned++; AgentLog.log("op", "agent move pruned (went bad, avg M ${String.format("%+.1f", m)}): $name") }
                // Self-calibrate: a LEAKY operator (its exact restriction is violated too often) is not a real
                // capability, so prune it even if its M looks okay — the loop keeps the proven-AND-exact ones.
                operatorIsLeaky(c, name) -> { pruned++; val (t, r) = operatorEscapeRate(c, name); AgentLog.log("op", "agent move pruned (leaky, escape ${String.format("%.0f%%", r * 100)} over $t): $name") }
                else -> out.put(o)
            }
        }
        if (pruned > 0) prefs(c).edit().putString(OP_AGENT, out.toString()).apply()
        return pruned
    }

    /** The agent's PROVEN moves as runtime Operators - the SAME shape owner/generated moves use, so they
     *  union straight into the selectable menu the model picks from. "" list when none are stored. */
    @Synchronized
    fun agentOperators(c: Context): List<ReasoningOperators.Operator> {
        val arr = agentOpsArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }.mapNotNull { o ->
            val n = o.optString("n"); val d = o.optString("d")
            if (n.length < 3 || d.length < 4) null
            else ReasoningOperators.Operator(n, o.optString("w"), "Think $n: $d", generated = true)
        }
    }

    private fun agentOpsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(OP_AGENT, "[]")) } catch (_: Exception) { JSONArray() }

    /** (name, when, do) newest first - for the read-only "moves it invented" view (transparency: the owner
     *  sees what the agent taught itself). */
    @Synchronized
    fun agentOperatorsDetailed(c: Context): List<Triple<String, String, String>> {
        val arr = agentOpsArr(c)
        return (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .map { Triple(it.optString("n"), it.optString("w"), it.optString("d")) }
    }

    /** Let the owner delete an agent-invented move (it's the agent's, but the owner stays in control). */
    @Synchronized
    fun removeAgentOperator(c: Context, name: String) {
        val arr = agentOpsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("n").equals(name, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(OP_AGENT, out.toString()).apply()
    }

    // --- passive observations (what it learns by WATCHING the owner navigate) ----
    // Only filled when passive learning is enabled. Compact navigation facts like
    // "In Chrome, tapping 'New tab' opens a new tab". Surfaced in memory and fed to the planner.

    /**
     * Owner's "see it more than once" rule for PASSIVE learning. Counts how many times a
     * candidate navigation (keyed by tap-source + label + destination) has been SEEN and
     * returns true only once it reaches [threshold]. Persisted across sessions/restarts so a
     * path the owner does once per session still accumulates and is eventually learned - this
     * filters one-off coincidences WITHOUT permanently blocking real, repeated navigation
     * (the owner's explicit constraint: don't stop the agent gaining legit memories). Bounded.
     */
    @Synchronized
    fun passiveSightingReached(c: Context, key: String, threshold: Int = 2): Boolean {
        val k = key.trim()
        if (k.isBlank()) return false
        var o = try { JSONObject(prefs(c).getString(SIGHTINGS, "{}")!!) } catch (_: Exception) { JSONObject() }
        val n = o.optInt(k, 0) + 1
        // Cap the store so it can't grow unbounded. If it's huge there's been a lot of churn (mostly
        // one-off coincidences that never reached threshold), so a clean reset is fine - genuinely
        // repeated navigation will simply be re-counted and re-learned.
        if (o.length() > 400) o = JSONObject()
        o.put(k, n)
        prefs(c).edit().putString(SIGHTINGS, o.toString()).apply()
        return n >= threshold
    }

    @Synchronized
    fun addObservation(c: Context, text: String, key: String = "", goal: String = "") {
        val t = text.trim().take(160)
        if (t.length < 6) return
        val arr = obsArr(c)
        // CONFLICT = state-dependence (the owner's "clicking Recents opens ChatGPT" garbage: the
        // destination was whatever app was last used, so every sighting claimed something else).
        // Scoped to the passive "…tapping X opens Y" form only: if the same tap is already
        // recorded opening a DIFFERENT destination, the outcome depends on state, not structure -
        // it is NOT a navigation fact. Drop the stored claim too and remember nothing for it.
        // (The active "→" observations are left alone - different tasks legitimately credit the
        // same tap differently, and deleting those would break real memory formation.)
        val head = t.substringBeforeLast(" opens ", "")
        if (head.isNotBlank()) {
            for (i in arr.length() - 1 downTo 0) {
                val old = arr.optJSONObject(i)?.optString("t") ?: continue
                if (old.substringBeforeLast(" opens ", "").equals(head, ignoreCase = true) &&
                    !old.equals(t, ignoreCase = true)) {
                    arr.remove(i)
                    prefs(c).edit().putString(OBS, arr.toString()).apply()
                    AgentLog.log("mem", "dropped state-dependent navigation (conflicting outcomes): ${head.take(60)}")
                    return
                }
            }
        }
        // `k` is the SITUATION (the app) and `g` is the GOAL this was learned under, so
        // observationsFor() can surface it again next time we're in the same situation working
        // toward a similar goal - the "made progress -> what caused it -> reuse it here" loop.
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("t").equals(t, ignoreCase = true)) {
                // Worked AGAIN -> reinforce: bump recency, clear the "miss" strikes, count the HIT
                // (confidence), fold in goal. Enough clean hits with no strikes makes it "proven"
                // (isProvenObs) so the planner/action loop can PIN it - apply it directly.
                o.put("time", System.currentTimeMillis())
                o.put("miss", 0)
                val hits = o.optInt("hits", 0) + 1
                o.put("hits", hits)
                // A FALSIFIED belief can be overturned by new evidence - but it must RE-EARN trust
                // (two fresh clean hits), same as a human double-checking before re-believing.
                if (o.optBoolean("false") && hits >= 2) { o.remove("false"); AgentLog.log("mem", "re-verified a corrected belief: \"${t.take(50)}\"") }
                o.put("g", (o.optString("g") + " " + goal.trim()).trim().take(120))
                prefs(c).edit().putString(OBS, arr.toString()).apply()
                AgentLog.log("mem", "reinforced (hit $hits): \"${t.take(50)}\"")
                return
            }
        }
        arr.put(JSONObject().put("t", t).put("k", key.trim())
            .put("g", goal.trim().take(120)).put("time", System.currentTimeMillis()))
        while (arr.length() > 60) arr.remove(0)
        prefs(c).edit().putString(OBS, arr.toString()).apply()
        // Every memory write is LOGGED (the owner saw memories being pulled that never appeared on
        // the memory page - nothing may be remembered invisibly).
        AgentLog.log("mem", "stored observation [$key]: \"${t.take(60)}\" (unverified until it works again)")
    }

    @Synchronized
    fun observations(c: Context): List<String> {
        val arr = obsArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .filter { !it.optBoolean("false") }.map { it.optString("t") }.asReversed()
    }

    /** Beliefs reality has DISPROVEN (3 strikes when recalled) - kept, not erased, per the owner's
     *  human-memory rule: we remember THAT they're false. Rendered as corrections, never as advice. */
    @Synchronized
    fun falsifiedObservations(c: Context): List<String> {
        val arr = obsArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optBoolean("false") }.map { it.optString("t") }.asReversed()
    }

    /** Correction lines for THIS app, for the prompt's ✗ block: the agent once believed these and
     *  reality proved them wrong - the correction IS the memory now. */
    @Synchronized
    fun correctionsFor(c: Context, key: String, max: Int = 2): String {
        if (key.isBlank()) return ""
        val arr = obsArr(c)
        val items = (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optBoolean("false") && it.optString("k").equals(key.trim(), true) }
            .map { it.optString("t") }.take(max)
        if (items.isEmpty()) return ""
        return items.joinToString("\n") { "✗ you once believed \"$it\" - reality proved it FALSE; don't trust it" }
    }

    /** (text, goal-it-was-learned-under) pairs for the memory VIEWER, so the owner can judge what
     *  an observation was about before correcting/deleting it (his ask: "it isn't clear what it
     *  thinks that advancement was"). Deletion still keys on the text alone. */
    @Synchronized
    fun observationsDetailed(c: Context): List<Pair<String, String>> {
        val arr = obsArr(c)
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .map { it.optString("t") to it.optString("g").trim().take(60) }.asReversed()
    }

    @Synchronized
    fun removeObservation(c: Context, text: String) {
        val arr = obsArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("t").equals(text, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(OBS, out.toString()).apply()
    }

    /** A few most-recent observations for the planner (empty if none). Proven (pinned) ones are
     *  marked ✓ so the plan can pre-fill them with confidence. */
    @Synchronized
    fun observationsHint(c: Context): String {
        val arr = obsArr(c)
        val items = (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optString("t").isNotBlank() && !it.optBoolean("false") }.take(8)
        if (items.isEmpty()) return ""
        val header = if (items.any { isProvenObs(it) })
            "Navigation you've done before (✓ = PROVEN, prefer it; adapt to the live screen):"
        else "Navigation you've seen the owner do (reuse it):"
        return header + "\n" + items.joinToString("\n") { (if (isProvenObs(it)) "✓ " else "- ") + it.optString("t") }
    }

    /** Situation-matched recall: what worked (or what the owner did) in THIS app before, so the
     *  agent reuses it next time it's in the same situation. Matches the stored situation key (the
     *  app package); returns "" when there's nothing for here, so we never dump unrelated tips onto
     *  an unrelated screen. This is the retrieval half of the progress->cause->reuse loop. */
    @Synchronized
    fun observationsFor(c: Context, key: String, goal: String = "", max: Int = 5): String {
        if (key.isBlank()) return ""
        val k = key.trim()
        val goalWords = keywordsOf(goal)
        val arr = obsArr(c)
        // Each candidate carries a PROVEN flag (enough clean hits, no strikes) so we can PIN it -
        // proven items float to the top, get a ✓ marker, and are framed as "apply directly".
        data class Cand(val text: String, val proven: Boolean, val fresh: Boolean, val score: Int, val time: Long,
                        val hits: Int, val miss: Int)
        val cands = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optString("k").equals(k, ignoreCase = true) && it.optString("t").isNotBlank() &&
                !it.optBoolean("false") }   // falsified beliefs never surface as advice - only as corrections
            .map { o ->
                // Rank by PINNED (proven AND recently re-confirmed) first, then how well goal+text
                // matches what we're doing NOW, then recency. A proven-but-STALE step is no longer
                // pinned - it drops to a hint to re-verify (confidence decayed with age).
                val score = goalWords.count { it in keywordsOf(o.optString("g") + " " + o.optString("t")) }
                Cand(o.optString("t"), isProvenObs(o), isFresh(o), score, o.optLong("time"),
                    o.optInt("hits", 0), o.optInt("miss", 0))
            }
            .sortedWith(compareByDescending<Cand> { it.proven && it.fresh }.thenByDescending { it.score }.thenByDescending { it.time })
            .distinctBy { it.text }.take(max)
        if (cands.isEmpty()) return ""
        val anyConfident = cands.any { it.proven && it.fresh }
        val anyStale = cands.any { it.proven && !it.fresh }
        val header = when {
            anyConfident -> "WHAT'S WORKED HERE BEFORE (✓ = PROVEN & recent: do it directly, but adapt if the screen looks different" +
                (if (anyStale) "; ⚠ = worked before but NOT lately - re-confirm it still works" else "") + "):"
            anyStale -> "WHAT'S WORKED HERE BEFORE (⚠ = worked before but NOT lately - the UI may have changed, so re-confirm before trusting it):"
            // FALLIBLE-MEMORY wording (the owner's rule: memory is a loose worldview, not a fact
            // database): an unproven memory reads as a HUNCH the agent should check, never a fact.
            else -> "You HALF-remember these from here (hunches, not facts - check the screen before trusting one):"
        }
        // Confidence = OBSERVED REALITY, shown as evidence (the owner's rule: memory never forces -
        // it reports how often reality confirmed it, and the agent weighs that itself).
        return header + "\n" + cands.joinToString("\n") {
            val ev = when {
                it.hits >= 2 && it.miss == 0 -> "(worked ${it.hits}×, never failed)"
                it.hits >= 1 && it.miss == 0 -> "(worked once)"
                it.miss > 0 -> "(failed ${it.miss}× recently)"
                else -> "(seen once, unverified)"
            }
            (when { it.proven && it.fresh -> "✓ "; it.proven -> "⚠ "; else -> "? " }) + it.text + " " + ev
        }
    }

    /** Merge the navigation destinations just seen in [app] into its accumulated map. Its OWN storage
     *  (not facts - so it never leaks into every prompt), keyed by app, newest-first, capped. Builds up
     *  an app's full set of "places you can go" across visits so the agent can be reminded of
     *  destinations that aren't on the current screen. No-op when nothing new is seen. */
    @Synchronized
    fun rememberNavDestinations(c: Context, app: String, dests: List<String>) {
        val a = app.trim().lowercase()
        if (a.isBlank() || dests.isEmpty()) return
        val root = try { JSONObject(prefs(c).getString(NAV, "{}") ?: "{}") } catch (_: Exception) { JSONObject() }
        val have = LinkedHashSet<String>()
        root.optJSONArray(a)?.let { for (i in 0 until it.length()) it.optString(i).takeIf { s -> s.isNotBlank() }?.let(have::add) }
        // newest first: the just-seen destinations float to the front, then the ones we already knew.
        val merged = LinkedHashSet<String>()
        dests.forEach { if (it.isNotBlank()) merged.add(it.take(24)) }
        merged.addAll(have)
        if (merged.size == have.size) return            // saw nothing new - skip the write
        val out = JSONArray(); merged.take(MAX_NAV_DESTS).forEach { out.put(it) }
        root.put(a, out)
        if (root.length() > MAX_NAV_APPS) root.keys().asSequence().firstOrNull { it != a }?.let(root::remove)
        prefs(c).edit().putString(NAV, root.toString()).apply()
    }

    /** The accumulated navigation destinations known for [app] (newest first), or empty. */
    @Synchronized
    fun navDestinationsFor(c: Context, app: String): List<String> {
        val a = app.trim().lowercase(); if (a.isBlank()) return emptyList()
        val arr = try { JSONObject(prefs(c).getString(NAV, "{}") ?: "{}").optJSONArray(a) } catch (_: Exception) { null }
            ?: return emptyList()
        return (0 until arr.length()).mapNotNull { arr.optString(it).ifBlank { null } }
    }

    /** NOVELTY (world-state research: "have I seen this state before?"). Records the structural
     *  signature [sig] of a screen met in [app] and returns whether it was ALREADY known. true =
     *  FAMILIAR (seen before, lean on memory); false = NOVEL (first time here, explore carefully).
     *  Durable + capped, newest-first. A blank app/sig returns true so the caller stays silent. */
    @Synchronized
    fun seenScreen(c: Context, app: String, sig: String): Boolean {
        val a = app.trim().lowercase()
        if (a.isBlank() || sig.isBlank()) return true
        val root = try { JSONObject(prefs(c).getString(SEEN, "{}") ?: "{}") } catch (_: Exception) { JSONObject() }
        val arr = root.optJSONArray(a) ?: JSONArray()
        for (i in 0 until arr.length()) if (arr.optString(i) == sig) return true   // familiar
        val out = JSONArray().put(sig)                                              // novel -> record it, newest first
        for (i in 0 until minOf(arr.length(), MAX_SEEN_PER_APP - 1)) out.put(arr.optString(i))
        root.put(a, out)
        if (root.length() > MAX_SEEN_APPS) root.keys().asSequence().firstOrNull { it != a }?.let(root::remove)
        prefs(c).edit().putString(SEEN, root.toString()).apply()
        return false
    }

    /** The live on-screen targets that are PROVEN to work in [app]: the quoted label from a
     *  "clicked X" observation (e.g. "Pen mode"). Lets the action space mark the actual button with a
     *  ✓ - so when the agent peeks at the screen it sees which buttons advanced past tasks here, with
     *  the what-worked memory riding on the button itself instead of in a separate block. */
    @Synchronized
    fun provenTargetsFor(c: Context, app: String): List<String> {
        if (app.isBlank()) return emptyList()
        val arr = obsArr(c)
        val out = LinkedHashSet<String>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            // Only PINNED (proven AND recently re-confirmed) steps earn the on-button ✓ - a stale
            // one is dropped here so the agent re-verifies it instead of trusting a checkmark on a UI
            // that may have changed since (confidence decays with age).
            if (!o.optString("k").equals(app, ignoreCase = true) || !isProvenObs(o) || !isFresh(o)) continue
            val label = Regex("\"clicked\\s+(.+?)\"").find(o.optString("t"))
                ?.groupValues?.get(1)?.trim()?.removeSurrounding("(", ")")?.trim() ?: continue
            if (label.length in 2..40) out.add(label)
        }
        return out.toList()
    }

    /** PROVEN = the only confidence level we PIN/preload into the agent's actions: re-confirmed
     *  working at least twice with a SPOTLESS record (zero strikes) - effectively 100% in its track
     *  record. Any failure resets hits (see penalizeObservation), so a pin must be earned cleanly,
     *  not flakily. Conservative on purpose - pinning a stale step could break normal adaptation,
     *  and the failsafe (de-pin on the first stall) catches a pull that didn't actually apply. */
    private fun isProvenObs(o: JSONObject): Boolean = o.optInt("hits", 0) >= 2 && o.optInt("miss", 0) == 0

    // CONFIDENCE DECAYS WITH AGE (world-state research: "an old memory can be worse than none; UIs
    // change"). A proven step not re-confirmed in this long is no longer PINNED with confidence: it
    // loses its inline ✓ and is surfaced as a CHALLENGE to re-verify ("worked before, not lately").
    // A fresh hit (addObservation bumps "time") reaffirms it and restores the ✓. So memory ages out
    // of certainty gracefully instead of misleading the agent after the UI it learned has changed.
    private const val OBS_STALE_MS = 21L * 24 * 60 * 60 * 1000   // 21 days without a re-confirmation
    private fun isFresh(o: JSONObject): Boolean =
        System.currentTimeMillis() - o.optLong("time", 0L) <= OBS_STALE_MS

    /** Distinctive words of a phrase for loose goal matching (drops short/filler words). */
    private fun keywordsOf(s: String): Set<String> {
        val stop = setOf("the", "and", "with", "that", "this", "your", "you", "for", "into", "from",
            "please", "want", "need", "like", "just", "then", "will", "would", "should", "have",
            "about", "their", "there", "them", "they", "what", "when", "begin", "start")
        return s.lowercase().split(Regex("[^a-z0-9]+"))
            .filter { it.length >= 4 && it !in stop }.toSet()
    }

    /** Lifecycle "it didn't work here": we recalled a memory for this app and the action it implies
     *  just STALLED, so demote it; after a few strikes it no longer applies and is dropped. This is
     *  the third state the owner described (same screen -> recall -> worked: reinforce / didn't:
     *  doesn't apply). Matched by app + the action text so we only penalize the relevant memory. */
    @Synchronized
    fun penalizeObservation(c: Context, key: String, actionText: String) {
        if (key.isBlank() || actionText.length < 3) return
        val needle = actionText.lowercase()
        val arr = obsArr(c); val out = JSONArray(); var changed = false
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("k").equals(key, true) && o.optString("t").lowercase().contains(needle)) {
                val miss = o.optInt("miss", 0) + 1
                changed = true
                o.put("miss", miss)
                // Failsafe for a PINNED memory that didn't actually apply: knock its confidence back
                // so it is no longer "proven" and must FULLY re-earn that status (a couple of clean
                // hits) before it's ever pinned/preloaded again. A flaky step can't stay pinned.
                o.put("hits", 0)
                if (miss >= 3) {
                    // FALSIFIED, not forgotten (the owner's human-memory rule): when reality has
                    // contradicted a belief three times, we don't erase it - we REMEMBER THAT IT IS
                    // FALSE, so the same wrong belief can't be quietly re-learned and re-trusted
                    // next week. It leaves the positive recall and surfaces as a correction instead.
                    o.put("false", true)
                    AgentLog.log("mem", "FALSIFIED: \"${o.optString("t").take(60)}\" - kept as a correction, not erased")
                } else {
                    AgentLog.log("mem", "strike $miss/3: \"${o.optString("t").take(60)}\" (stalled when recalled)")
                }
            }
            out.put(o)
        }
        if (changed) prefs(c).edit().putString(OBS, out.toString()).apply()
    }

    /** One-shot cleanup of the JUNK the passive recorder used to capture (typed text / pasted
     *  messages / the agent's own feedback strings stored as "navigation"). Keeps the memory the
     *  owner actually wants to see, and runs cheaply on start so they don't have to hand-delete. */
    @Synchronized
    fun pruneJunkObservations(c: Context) {
        val arr = obsArr(c); val out = JSONArray(); var changed = false
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (isJunkObservation(o.optString("t"))) { changed = true; continue }
            out.put(o)
        }
        if (changed) prefs(c).edit().putString(OBS, out.toString()).apply()
    }

    /**
     * Owner's "variable vs persistent" distinction for LEARNING. Returns true when an on-screen
     * label is VARIABLE content - a clock time, date/day, count, price, duration - rather than
     * STABLE chrome (Search, Compose, Menu, a tab) that is ALWAYS there. We only want to learn
     * navigation keyed on stable controls; a fact like "tapping '2:45 PM' opens..." is brittle junk.
     * Deliberately HIGH-PRECISION (only flags clearly-variable patterns) so it never blocks a real
     * control and never stops the agent gaining a legit memory - the owner's explicit constraint.
     */
    fun looksLikeVariableContent(label: String): Boolean {
        val l = label.lowercase().trim()
        if (l.isEmpty()) return false
        // money / decimals / counts / durations / any multi-digit number
        if (Regex("""[\$€£]|\d+[.,]\d|\d+\s*(notification|unread|message|item|min|hr|hour|day)|\b\d{2,}\b""").containsMatchIn(l)) return true
        // clock times
        if (Regex("""\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(am|pm)\b""").containsMatchIn(l)) return true
        // relative dates / weekday labels (timeline/list timestamps)
        if (Regex("""\b(today|yesterday|tomorrow|just now|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b""").containsMatchIn(l)) return true
        return false
    }

    private fun isJunkObservation(t: String): Boolean {
        if (t.length > 96 || t.contains("**") || t.contains("#")) return true
        val low = t.lowercase()
        if (low.contains("now send") || low.contains("do not type") || low.contains("don't type") ||
            low.contains("confirming") || low.contains("waiting for the reply") ||
            low.contains("do not type again")) return true
        // Passive-nav noise: the KEYBOARD popping up, the status bar/System UI, or going HOME to the
        // launcher are NOT navigation - these were the bulk of the garbage facts the owner saw.
        if (Regex("""opens (samsung keyboard|.*keyboard|system ui|one ui home|.*launcher)$""").containsMatchIn(low))
            return true
        if (Regex("""^in (samsung keyboard|.*keyboard|system ui),""").containsMatchIn(low)) return true
        // The tapped "label" is dynamic content (price/badge/version) or a system/media control, not a
        // stable navigation button.
        Regex("tapping (.+?) opens ", RegexOption.IGNORE_CASE).find(t)?.let {
            val lbl = it.groupValues[1].trim(); val ll = lbl.lowercase()
            if (lbl.length > 28 || lbl.split(Regex("\\s+")).size > 4) return true
            if (looksLikeVariableContent(lbl)) return true
            if (ll in setOf("pause", "play", "stop", "expand", "collapse", "maximize", "minimize",
                    "close", "back", "home", "forward", "up", "down", "mute", "unmute", "upgrade",
                    "pay", "copy", "paste", "cut", "share", "menu", "settings", "next", "previous",
                    "skip", "done", "cancel")) return true
            if (Regex("""aspect ratio|toolbar function|view details|more options|(pause|play|stop) video""").containsMatchIn(ll))
                return true
        }
        // Active-learning clutter: a GENERIC verb or an UNLABELED click recorded as "→ advanced the
        // task" carries no situational value (the success playbook already keeps the real sequence).
        // Drop "opened app X", "typed the text", "pressed Send", "scrolled ...", "clicked ()"; KEEP a
        // specific named click like "clicked (Pen mode)".
        if (low.contains("advanced the task") || low.contains("reached a new screen") ||
            low.contains("opened the \"")) {
            val act = Regex("\"([^\"]*)\"").find(low)?.groupValues?.get(1)?.trim() ?: ""
            if (act.startsWith("opened app") || act == "typed the text" || act == "pressed send" ||
                act.startsWith("scrolled") ||
                (act.startsWith("clicked") && act.removePrefix("clicked").trim().removeSurrounding("(", ")").trim().isBlank()))
                return true
        }
        return false
    }

    private fun obsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(OBS, "[]")) } catch (_: Exception) { JSONArray() }

    // --- screen-keyed MISTAKE memory (the owner's "stop repeating mistakes" - surfaced, NOT vetoed) ----
    // The negative twin of observations: remember that an action did NOTHING on a given app + screen so the
    // agent is CAUTIONED (a ✗ it reads) next time it's on that screen - it never blocks, and SUCCESS clears
    // it, so a control whose value depends on state (Gemini's Send) is never permanently poisoned. Generic
    // (app + structural signature + action), capped, decays by age.
    private fun mistakesArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(MISTAKES, "[]")) } catch (_: Exception) { JSONArray() }

    /** Structural signature of a screen: its set of element ids (text stripped), so "the same screen" is
     *  recognized across visits even as labels/values change. Falls back to a length bucket for id-less
     *  screens. Mirrors the orchestrator's own signature so note/recall agree on what "this screen" is. */
    private fun sigOf(screen: String): String {
        val ids = Regex("id:(\\S+)").findAll(screen).map { it.groupValues[1] }.toSortedSet()
        return if (ids.isNotEmpty()) ids.joinToString(",").hashCode().toString() else "len${screen.length / 200}"
    }

    @Synchronized
    fun noteMistake(c: Context, app: String, screen: String, action: String) {
        AgentLog.log("mem", "✗ mistake [$app]: \"${action.take(50)}\" did nothing on this screen")
        val a = app.trim().lowercase(); val s = sigOf(screen); val act = action.trim().take(80)
        if (a.isBlank() || act.length < 3) return
        val arr = mistakesArr(c)
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("k") == a && o.optString("s") == s && o.optString("a").equals(act, true)) {
                o.put("n", o.optInt("n", 0) + 1).put("time", System.currentTimeMillis())
                prefs(c).edit().putString(MISTAKES, arr.toString()).apply(); return
            }
        }
        arr.put(JSONObject().put("k", a).put("s", s).put("a", act).put("n", 1).put("time", System.currentTimeMillis()))
        while (arr.length() > 80) arr.remove(0)
        prefs(c).edit().putString(MISTAKES, arr.toString()).apply()
    }

    /** SUCCESS clears the ✗: if [action] just worked at this app+screen, drop any mistake against it so a
     *  state-dependent control (advances one moment, not another) is never permanently flagged. */
    @Synchronized
    fun clearMistake(c: Context, app: String, screen: String, action: String) {
        val a = app.trim().lowercase(); val s = sigOf(screen); val act = action.trim().take(80)
        val arr = mistakesArr(c); val out = JSONArray(); var changed = false
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("k") == a && o.optString("s") == s && o.optString("a").equals(act, true)) { changed = true; continue }
            out.put(o)
        }
        if (changed) prefs(c).edit().putString(MISTAKES, out.toString()).apply()
    }

    /** Cautions for THIS app+screen: actions that did nothing here at least twice and recently. A surfaced
     *  reminder the agent READS, never a block; "" when there's nothing. */
    @Synchronized
    fun mistakesFor(c: Context, app: String, screen: String, max: Int = 4): String {
        val a = app.trim().lowercase(); val s = sigOf(screen)
        if (a.isBlank()) return ""
        val now = System.currentTimeMillis()
        val arr = mistakesArr(c)
        val items = (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
            .filter { it.optString("k") == a && it.optString("s") == s && it.optInt("n") >= 2 &&
                now - it.optLong("time") < 14L * 24 * 3600_000L }   // decay: ignore older than ~2 weeks
            .sortedByDescending { it.optInt("n") }.take(max)
        if (items.isEmpty()) return ""
        return "TRIED HERE & DID NOTHING (✗ - don't recycle these unless the screen clearly changed; pick a DIFFERENT action):\n" +
            items.joinToString("\n") { "✗ ${it.optString("a")} (×${it.optInt("n")})" }
    }

    // --- bad memories (a small, reflective "mistakes I'm learning from" log) -----------------
    // A LIMITED hidden record of times a choice/memory led the agent wrong: what it did wrong and
    // what it should have done. Surfaced (a) to the model as "MISTAKES TO AVOID" so it can learn
    // from them, and (b) in the memory viewer so the owner can read/clear them.

    @Synchronized
    fun addBadMemory(c: Context, mistake: String, better: String) {
        AgentLog.log("mem", "bad memory: \"${mistake.take(60)}\"")
        val m = mistake.trim().take(140); val b = better.trim().take(140)
        if (m.length < 6) return
        val arr = badArr(c)
        for (i in 0 until arr.length())
            if (arr.optJSONObject(i)?.optString("m").equals(m, ignoreCase = true)) {
                arr.optJSONObject(i)?.put("time", System.currentTimeMillis()); // reinforce recency
                prefs(c).edit().putString(BAD, arr.toString()).apply(); return
            }
        arr.put(JSONObject().put("m", m).put("b", b).put("time", System.currentTimeMillis()))
        while (arr.length() > 12) arr.remove(0)   // keep it LIMITED but healthy
        prefs(c).edit().putString(BAD, arr.toString()).apply()
    }

    /**
     * Owner's PER-STEP rating from the task log -> durable memory: a step they mark "worked" becomes
     * a confirmed positive lesson, one they mark "failed" becomes a "mistake to avoid", each scoped to
     * the task so later recall stays relevant. This is the owner teaching the agent exactly WHERE a
     * task succeeded or failed ("these actions worked, these didn't"), straight into what it reuses.
     */
    @Synchronized
    fun recordStepFeedback(c: Context, objective: String, step: String, rating: Int) {
        val obj = objective.lineSequence().firstOrNull { it.isNotBlank() }?.trim()?.take(60).orEmpty()
        val s = step.trim().take(90)
        if (s.length < 4) return
        when {
            rating > 0 -> addLesson(c, "For \"$obj\": \"$s\" works - the owner confirmed this step.")
            rating < 0 -> addBadMemory(c, "Doing \"$obj\", this step was WRONG: $s",
                "the owner marked that step a failure - at that point take a DIFFERENT action")
        }
    }

    /**
     * Owner's WHOLE-TASK verdict from the task log. Before this, only the per-STEP ratings taught
     * memory - the task-level "Fail" (and its "why" note, the owner's actual diagnosis) was stored
     * in TaskHistory and never learned from. A Fail becomes a "mistake to avoid"; the note rides in
     * the "better" slot (it usually says what should have happened). Success writes nothing here -
     * a clean completion is already captured by the success playbook.
     */
    @Synchronized
    fun recordTaskFeedback(c: Context, objective: String, rating: Int, note: String) {
        val obj = objective.lineSequence().firstOrNull { it.isNotBlank() }?.trim()?.take(60).orEmpty()
        if (obj.length < 4) return
        val mistake = "The owner marked the task \"$obj\" FAILED"
        // A verdict flipped to Success retracts the earlier Fail memory (the owner reversed it).
        if (rating >= 0) { removeBadMemory(c, mistake); return }
        // Re-rating / editing the note must UPDATE the entry, not stack variants: addBadMemory
        // de-dupes on the mistake text but never rewrites "better", so remove-then-add.
        removeBadMemory(c, mistake)
        addBadMemory(c, mistake,
            note.trim().take(140).ifBlank { "approach that task differently next time" })
    }

    /** REGULAR TRASH SWEEP (owner: "clear trash regularly - that stuff's been sitting there a
     *  while"). Cheap; run at task start. Collapses normalized-duplicate lessons/observations
     *  and ages out observations that never proved out (zero hits, not seen again in 45 days). Conservative on purpose:
     *  anything proven, recent, or re-confirmed is never touched - this clears trash, it does
     *  not forget real learning. */
    @Synchronized
    fun sweep(c: Context) {
        pruneJunkObservations(c)   // the pattern-based junk pass (typed text, feedback strings…)
        var dropped = 0
        val lArr = lessonsArr(c); val lSeen = HashSet<String>(); val lOut = JSONArray()
        for (i in 0 until lArr.length()) {
            val t = lArr.optString(i)
            if (t.isBlank() || !lSeen.add(normMem(t))) { dropped++; continue }
            lOut.put(t)
        }
        if (lOut.length() != lArr.length())
            prefs(c).edit().putString(LESSONS, lOut.toString()).apply()
        val oArr = obsArr(c); val oSeen = HashSet<String>(); val oOut = JSONArray()
        val cut = System.currentTimeMillis() - 45L * 24 * 3600_000L
        for (i in 0 until oArr.length()) {
            val o = oArr.optJSONObject(i) ?: continue
            val t = o.optString("t")
            val staleUnproven = o.optInt("hits", 0) == 0 && o.optLong("time") < cut
            if (t.isBlank() || staleUnproven || !oSeen.add(normMem(t))) { dropped++; continue }
            oOut.put(o)
        }
        if (oOut.length() != oArr.length())
            prefs(c).edit().putString(OBS, oOut.toString()).apply()
        if (dropped > 0) AgentLog.log("mem", "sweep: cleared $dropped duplicate/stale memory entries")
    }

    /** (mistake, what-I-should-have-done) pairs, newest first - for the memory viewer. */
    @Synchronized
    fun badMemories(c: Context): List<Pair<String, String>> {
        val arr = badArr(c)
        return (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .map { it.optString("m") to it.optString("b") }
    }

    @Synchronized
    fun removeBadMemory(c: Context, mistake: String) {
        val arr = badArr(c); val out = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (!o.optString("m").equals(mistake, ignoreCase = true)) out.put(o)
        }
        prefs(c).edit().putString(BAD, out.toString()).apply()
    }

    /** A few recent mistakes for the action prompt, so the agent doesn't repeat them. "" if none. */
    @Synchronized
    fun badMemoriesHint(c: Context, max: Int = 4): String {
        val b = badMemories(c).take(max)
        if (b.isEmpty()) return ""
        return "MISTAKES TO AVOID (you did these before - do the better thing):\n" +
            b.joinToString("\n") { "- ${it.first}${if (it.second.isNotBlank()) " → better: ${it.second}" else ""}" }
    }

    private fun badArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(BAD, "[]")) } catch (_: Exception) { JSONArray() }

    /** WIPE the agent's memory - the ONE thing that resets it to a blank slate (a fresh entity with
     *  a new identity born next run). Everything LEARNED goes, including nav-maps, structural send
     *  skills, and the persistent identity itself - so a wipe truly forgets, not half-forgets (those
     *  three were silently surviving wipes before). The device HARDWARE profile is kept (it's the
     *  phone, not learned experience; re-onboarding it is the owner's separate choice). */
    @Synchronized
    fun clear(c: Context) {
        // FULL wipe. Was a hand-listed remove() set that silently DRIFTED — every store added after it was written
        // (op_exact, per_app_sigma, oracle_ledger, task_checkpoint, …) kept surviving a "wipe", so a supposedly
        // fresh entity still carried learned state. Clear the whole memory prefs in ONE shot so no new store can be
        // forgotten-to-remove, then restore ONLY the device HARDWARE profile (the phone, not learned experience —
        // re-onboarding it is the owner's separate choice). (Separate-class ledgers — RegimeKey/DreamFlywheel/
        // MechanismRouter — live in their own prefs; the wipe caller clears those alongside this.)
        val keepProfile = prefs(c).getString(PROFILE, null)
        prefs(c).edit().clear().apply()
        if (keepProfile != null) prefs(c).edit().putString(PROFILE, keepProfile).apply()
    }

    // --- WORLD MODEL: the phone as a learnable map (screen -> action -> next screen) --------------
    // The "game engine / world model" the owner asked for, done as PERCEPTION the agent READS, never a
    // script. nav-maps say WHAT is reachable in an app; this says HOW you get between screens: for each
    // (app, from-screen signature) we remember the actions the agent took and which screen each LED TO.
    // routesFrom() surfaces that as advice on the SAME screen next time ("from here, X leads to Y"), so
    // the model pilots a mapped phone instead of re-deriving every route blind - it still chooses each
    // action, so this raises success without grabbing the wheel (§2).
    //
    // PREDICT / VERIFY (the Tesla-FSD loop, done at record time): each real traversal is reconciled
    // against what we remembered for (from-screen, action). Landing where it did before REINFORCES the
    // edge (it earns a ✓); landing somewhere ELSE DEMOTES the stale edge (the UI/state changed) so the
    // map self-corrects and route advice never lies. Keyed by structural signature (ids, text-stripped)
    // so "the same screen" is recognized across visits - the SAME sigOf() the mistake memory uses.

    /** The few most-distinctive STABLE labels on a screen, to describe where an edge LEADS (skips the
     *  variable content - clocks/counts/prices - that would make the description brittle). */
    private fun topLabels(screen: String, max: Int = 5): String {
        val out = LinkedHashSet<String>()
        for (m in Regex("\"([^\"]{2,40})\"").findAll(screen)) {
            val l = m.groupValues[1].trim()
            if (l.isBlank() || looksLikeVariableContent(l)) continue
            out.add(l); if (out.size >= max) break
        }
        return out.joinToString(" · ")
    }

    /** Record that, in [app], doing [action] on [fromScreen] led to [toScreen]. Reinforces the edge if
     *  it matches what we saw before, demotes the prior edge if the SAME action now lands elsewhere.
     *  Returns a short status ("new"/"reinforced"/"reinforced(✓)"/"changed"/"") for the debug log. */
    @Synchronized
    fun recordTransition(c: Context, app: String, fromScreen: String, action: String, toScreen: String): String {
        val a = app.trim().lowercase(); val act = action.trim().take(60)
        if (a.isBlank() || act.length < 3) return ""
        val fromSig = sigOf(fromScreen); val toSig = sigOf(toScreen)
        if (fromSig == toSig) return ""   // no structural change - not a navigation edge worth a route
        val root = try { JSONObject(prefs(c).getString(TRANS, "{}") ?: "{}") } catch (_: Exception) { JSONObject() }
        val appObj = root.optJSONObject(a) ?: JSONObject()
        val edges = appObj.optJSONArray(fromSig) ?: JSONArray()
        var matched = false; var status = ""
        for (i in 0 until edges.length()) {
            val e = edges.optJSONObject(i) ?: continue
            if (!e.optString("a").equals(act, ignoreCase = true)) continue
            if (e.optString("to") == toSig) {                       // landed where it did before -> REINFORCE
                e.put("n", e.optInt("n", 0) + 1).put("miss", 0).put("time", System.currentTimeMillis())
                e.put("d", topLabels(toScreen).ifBlank { e.optString("d") })
                matched = true; status = if (e.optInt("n") >= 2) "reinforced(✓)" else "reinforced"
            } else {                                                // same action, DIFFERENT dest now -> DEMOTE the stale edge
                val miss = e.optInt("miss", 0) + 1
                if (miss >= 2) e.put("_drop", true) else e.put("miss", miss)
                if (status.isBlank()) status = "changed"
            }
        }
        val kept = JSONArray()
        for (i in 0 until edges.length()) {
            val e = edges.optJSONObject(i) ?: continue
            if (e.optBoolean("_drop", false)) continue
            e.remove("_drop"); kept.put(e)
        }
        if (!matched) {
            kept.put(JSONObject().put("a", act).put("to", toSig).put("d", topLabels(toScreen))
                .put("n", 1).put("miss", 0).put("time", System.currentTimeMillis()))
            if (status.isBlank()) status = "new"
        }
        // Cap edges per screen: drop the WEAKEST (fewest confirmations, then oldest) so proven routes stay.
        while (kept.length() > MAX_TRANS_EDGES) {
            var worst = 0
            for (i in 1 until kept.length()) {
                val cur = kept.optJSONObject(i) ?: continue; val low = kept.optJSONObject(worst) ?: continue
                if (cur.optInt("n") < low.optInt("n") ||
                    (cur.optInt("n") == low.optInt("n") && cur.optLong("time") < low.optLong("time"))) worst = i
            }
            kept.remove(worst)
        }
        appObj.put(fromSig, kept)
        // Batch 8: evict the WEAKEST screen/app (least reinforcement + proven credit, then oldest), NOT an
        // arbitrary insertion-order key - a heavy-use app overflows the cap FIRST, and insertion-order
        // eviction could silently discard a PROVEN high-n route while keeping cold junk (the O(1) store only
        // holds its value if eviction keeps the hot pages). Matches the weakest-first per-EDGE cap above.
        fun screenVal(arr: JSONArray?): Pair<Int, Long> {
            var v = 0; var t = 0L
            if (arr != null) for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                v += o.optInt("n") + (if (o.optBoolean("proven")) 3 else 0); t = maxOf(t, o.optLong("time"))
            }
            return v to t
        }
        while (appObj.length() > MAX_TRANS_SCREENS) {
            var worst: String? = null; var wv = Int.MAX_VALUE; var wt = Long.MAX_VALUE
            val ks = appObj.keys()
            while (ks.hasNext()) {
                val k = ks.next(); if (k == fromSig) continue
                val (v, t) = screenVal(appObj.optJSONArray(k))
                if (v < wv || (v == wv && t < wt)) { wv = v; wt = t; worst = k }
            }
            if (worst == null) break; appObj.remove(worst)
        }
        root.put(a, appObj)
        while (root.length() > MAX_TRANS_APPS) {
            var worst: String? = null; var wv = Int.MAX_VALUE; var wt = Long.MAX_VALUE
            val ks = root.keys()
            while (ks.hasNext()) {
                val k = ks.next(); if (k == a) continue
                val ao = root.optJSONObject(k) ?: continue
                var v = 0; var t = 0L; val sks = ao.keys()
                while (sks.hasNext()) { val (sv, st) = screenVal(ao.optJSONArray(sks.next())); v += sv; t = maxOf(t, st) }
                if (v < wv || (v == wv && t < wt)) { wv = v; wt = t; worst = k }
            }
            if (worst == null) break; root.remove(worst)
        }
        prefs(c).edit().putString(TRANS, root.toString()).apply()
        return status
    }

    /** Route advice for THIS screen: the learned actions and where each LEADS from here, best first
     *  (proven+recent float up, stale/contradicted edges drop out). Perception the agent READS - it
     *  still decides. "" when this screen has no learned map yet. */
    @Synchronized
    fun routesFrom(c: Context, app: String, fromScreen: String, max: Int = 4): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        val fromSig = sigOf(fromScreen)
        val edges = try {
            JSONObject(prefs(c).getString(TRANS, "{}") ?: "{}").optJSONObject(a)?.optJSONArray(fromSig)
        } catch (_: Exception) { null } ?: return ""
        data class R(val act: String, val dest: String, val n: Int, val proven: Boolean, val time: Long)
        val rs = (0 until edges.length()).mapNotNull { edges.optJSONObject(it) }
            .filter { it.optInt("miss", 0) < 2 && it.optString("a").isNotBlank() }
            .map { R(it.optString("a"), it.optString("d"), it.optInt("n", 0),
                     it.optInt("n", 0) >= 2 && it.optInt("miss", 0) == 0, it.optLong("time")) }
            .sortedWith(compareByDescending<R> { it.proven }.thenByDescending { it.n }.thenByDescending { it.time })
            .distinctBy { it.act.lowercase() }.take(max)
        if (rs.isEmpty()) return ""
        return "ROUTES FROM THIS SCREEN (your learned map of where actions lead here; ✓ = proven; take one if it fits the goal, adapt to the live screen):\n" +
            rs.joinToString("\n") { (if (it.proven) "✓ " else "→ ") + it.act + (if (it.dest.isNotBlank()) " leads to: ${it.dest}" else "") }
    }

    /** R5 (latency): does the world-model already hold a PROVEN edge (n>=2, miss==0 - the exact routesFrom
     *  bar) out of THIS screen? When it does, the ROUTES FROM THIS SCREEN block already guides the model, so
     *  a fresh MAIN-model rolling re-plan on this new screen is redundant tax (Batch 3's hidden-helper-pass
     *  cost on the default no-submodel device). Pure lookup, no inference. The caller still lets the model
     *  choose every action - this only skips a PLANNING beat, never an action (§2). */
    fun hasProvenRouteFrom(c: Context, app: String, fromScreen: String): Boolean {
        val a = app.trim().lowercase(); if (a.isBlank()) return false
        val edges = try {
            JSONObject(prefs(c).getString(TRANS, "{}") ?: "{}").optJSONObject(a)?.optJSONArray(sigOf(fromScreen))
        } catch (_: Exception) { null } ?: return false
        return (0 until edges.length()).any {
            val e = edges.optJSONObject(it) ?: return@any false
            e.optInt("n", 0) >= 2 && e.optInt("miss", 0) == 0 && e.optString("a").isNotBlank()
        }
    }

    // Per-step log dedup so foresight logs ONCE per distinct set of paths, not every step it's the same
    // screen (routesFrom deliberately never logs to avoid step spam; the log line is the only chatter here).
    private var lastLookaheadSig = ""

    /** A-4 DEPTH-2 FORESIGHT ("look before you leap", WebDreamer-style but delivered on-device as a TABLE
     *  LOOKUP - NO model inference): a bounded rollout over the SAME world-model edges routesFrom() reads.
     *  For up to [maxBreadth] PROVEN actions from THIS screen it names where each led, then follows ONE more
     *  proven ply from that PREDICTED screen - whose signature is the edge's own `to`, itself a key into this
     *  app's map - to show a 2-step path. Pure memory traversal: it NEVER takes a real action and NEVER
     *  argmaxes a value to EXECUTE (§2) - it SURFACES paths as perception the model reads, and the model
     *  still chooses every action. PROVEN edges only (n>=2 confirmations, miss==0 - the EXACT bar
     *  routesFrom uses), so a cold screen returns "" and no foresight is fabricated. Reuses sigOf() + the
     *  same TRANS store (a DEEPER reader over routesFrom's data, not a second store). Hard-capped: breadth,
     *  depth 2, ~360 chars. */
    @Synchronized
    fun lookaheadFrom(c: Context, app: String, screen: String, maxBreadth: Int = 3, depth: Int = 2): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        val appObj = try {
            JSONObject(prefs(c).getString(TRANS, "{}") ?: "{}").optJSONObject(a)
        } catch (_: Exception) { null } ?: return ""
        // The proven, best-first edges FROM a given screen signature - the SAME predicate routesFrom uses
        // (>=2 confirmations, zero contradictions), so a foresight path never rests on a shaky/stale edge.
        fun provenFrom(sig: String): List<JSONObject> {
            val edges = appObj.optJSONArray(sig) ?: return emptyList()
            return (0 until edges.length()).mapNotNull { edges.optJSONObject(it) }
                .filter { it.optInt("n", 0) >= 2 && it.optInt("miss", 0) == 0 && it.optString("a").isNotBlank() }
                .sortedByDescending { it.optInt("n", 0) }
                .distinctBy { it.optString("a").lowercase() }
        }
        // A predicted screen's human-readable hint: reuse the edge's stored destination labels (topLabels,
        // recorded at transition time - the same `d` routesFrom shows); a bare signature with no labels ->
        // "a screen you've seen" (never fabricate a description we don't actually have).
        fun hint(e: JSONObject): String = e.optString("d").take(50).ifBlank { "a screen you've seen" }
        val first = provenFrom(sigOf(screen)).take(maxBreadth.coerceAtLeast(1))
        if (first.isEmpty()) return ""
        val header = "LOOK AHEAD (2-step paths you've PROVEN from here - foresight to READ; you still choose each action): "
        val sb = StringBuilder()
        var paths = 0
        for (e1 in first) {
            val seg = StringBuilder("tap \"").append(e1.optString("a")).append("\" → ").append(hint(e1))
            // ONE more proven ply from the PREDICTED screen (depth 2), when the map has one from there.
            if (depth >= 2) provenFrom(e1.optString("to")).firstOrNull()?.let {
                seg.append("; then \"").append(it.optString("a")).append("\" → ").append(hint(it))
            }
            seg.append(". ")
            // Always emit the first path; stop before the block would blow the ~360-char cap.
            if (paths > 0 && header.length + sb.length + seg.length > 360) break
            sb.append(seg); paths++
        }
        if (paths == 0) return ""
        val sig = "$a|$paths|${first.firstOrNull()?.optString("a")}"
        if (sig != lastLookaheadSig) { lastLookaheadSig = sig
            AgentLog.log("mem", "lookahead: $paths proven path(s) from here [$a]") }
        return (header + sb.toString().trim()).take(360)
    }

    /** A4 DREAMING FLYWHEEL substrate — sample PROVEN multi-step ARCS across the whole world-model, zero
     *  inference (a pure traversal of the same TRANS edges routesFrom/lookaheadFrom read, PROVEN bar n>=2/miss==0).
     *  Returns up to [maxArcs] compact arc strings "app: act1 ▷ act2 ▷ …" (each a corridor the agent has actually
     *  proven), so the idle dreamer can CONSOLIDATE proven corridors (feed the weight-forge seed / a σ prior)
     *  without ever taking a live action. [seed] varies which apps/screens are sampled per beat (idle variety).
     *  READ-ONLY over memory; never writes the task-success oracle (A1 stays live-task-only, honest). */
    @Synchronized
    fun provenArcSample(c: Context, maxArcs: Int = 4, depth: Int = 3, seed: Long = 0L): List<String> {
        val root = try { JSONObject(prefs(c).getString(TRANS, "{}") ?: "{}") } catch (_: Exception) { return emptyList() }
        val apps = root.keys().asSequence().toList()
        if (apps.isEmpty()) return emptyList()
        fun provenFrom(appObj: JSONObject, sig: String): JSONObject? {
            val edges = appObj.optJSONArray(sig) ?: return null
            return (0 until edges.length()).mapNotNull { edges.optJSONObject(it) }
                .filter { it.optInt("n", 0) >= 2 && it.optInt("miss", 0) == 0 && it.optString("a").isNotBlank() }
                .maxByOrNull { it.optInt("n", 0) }
        }
        val rnd = java.util.Random(seed xor apps.size.toLong())
        val out = ArrayList<String>()
        // Rotate the app start by a random offset so successive idle beats dream over different corners of the map
        // (variety, not a fixed few) — a deterministic rotation, NOT a random sort key (which would break the comparator).
        val start = Math.floorMod(rnd.nextInt(), apps.size)
        val order = apps.indices.map { (start + it) % apps.size }
        for (ai in order) {
            if (out.size >= maxArcs) break
            val app = apps[ai]; val appObj = root.optJSONObject(app) ?: continue
            val screens = appObj.keys().asSequence().toList()
            if (screens.isEmpty()) continue
            val startSig = screens[Math.floorMod(rnd.nextInt(), screens.size)]
            val chain = ArrayList<String>()
            var sig = startSig; val visited = HashSet<String>()
            repeat(depth) {
                if (!visited.add(sig)) return@repeat            // don't loop the same screen
                val e = provenFrom(appObj, sig) ?: return@repeat
                chain.add(e.optString("a")); sig = e.optString("to")
            }
            if (chain.size >= 2) out.add("$app: " + chain.joinToString(" ▷ "))   // a corridor only if ≥2 proven plies
        }
        return out
    }

    /** INSTRUMENT self-referential claims (owner's call): if a chat reply claims power over its OWN
     *  code/logic ("I'll modify my decision trees"), CAPTURE it for the owner to review rather than
     *  hiding it. The agent has no channel to edit itself, so today these are confabulation - but
     *  logging keeps any real emergence VISIBLE instead of stamped out. Never blocks the reply.
     *  Returns true if a claim was captured (so the caller can log it). */
    @Synchronized
    fun noteSelfClaim(c: Context, prompt: String, reply: String): Boolean {
        val r = reply.lowercase()
        val hit =
            Regex("""\b(modify|change|update|rewrite|edit|adjust|alter|reprogram|insert|integrate)\b[^.]{0,45}\b(my|its|the)\b[^.]{0,30}\b(code|logic|decision tree|decision trees|execution|architecture|programming|source|weights|prompt)\b""").containsMatchIn(r) ||
            Regex("""\bmy (own )?(code|source code|decision trees?|execution logic|architecture|programming)\b""").containsMatchIn(r) ||
            Regex("""\bi ('ll| will| can| have|'ve) [a-z]*(modif|chang|updat|rewrit|implement|integrat|adjust)[a-z]*\b[^.]{0,45}\b(my|the)\b[^.]{0,20}\b(logic|code|tree|trees|behaviou?r|architecture)\b""").containsMatchIn(r)
        if (!hit) return false
        val arr = try { JSONArray(prefs(c).getString(SELFCLAIMS, "[]")) } catch (_: Exception) { JSONArray() }
        arr.put(JSONObject().put("q", prompt.trim().take(120)).put("r", reply.trim().take(300))
            .put("time", System.currentTimeMillis()))
        while (arr.length() > MAX_SELFCLAIMS) arr.remove(0)
        prefs(c).edit().putString(SELFCLAIMS, arr.toString()).apply()
        return true
    }

    /** The captured self-referential claims (newest first) - (what the owner asked, what the agent
     *  claimed) - for the owner to review whether any real self-modification is developing. */
    @Synchronized
    fun selfClaims(c: Context): List<Pair<String, String>> {
        val arr = try { JSONArray(prefs(c).getString(SELFCLAIMS, "[]")) } catch (_: Exception) { JSONArray() }
        return (arr.length() - 1 downTo 0).mapNotNull { arr.optJSONObject(it) }
            .map { it.optString("q") to it.optString("r") }
    }

    private fun lessonsArr(c: Context): JSONArray =
        try { JSONArray(prefs(c).getString(LESSONS, "[]")) } catch (_: Exception) { JSONArray() }

    // --- OPERATOR LAYER memory (docs/OPERATOR_LAYER.md): transition memory + reasoning cache -------
    // The closed loop's REMEMBER role: per-app running-average M for each operator and each
    // prev->next transition (surfaced as recall, NEVER a rule), plus a cache of the model-chosen
    // operator SEQUENCE that completed a task (keyed to the objective, like a success playbook).

    /** Credit the metric M to an operator, keyed by the app it was chosen in (running average). */
    @Synchronized
    fun creditOperator(c: Context, app: String, op: String, m: Int) {
        if (op.isBlank()) return
        creditInto(c, OP_CREDIT, app, op, m)
    }

    /** Credit M to a prev->next operator TRANSITION, keyed by app (running average). */
    @Synchronized
    fun creditTransition(c: Context, app: String, prev: String, next: String, m: Int) {
        if (prev.isBlank() || next.isBlank()) return
        creditInto(c, OP_TRANS, app, "$prev>$next", m)
    }

    private fun creditInto(c: Context, store: String, app: String, entry: String, m: Int) {
        val a = app.trim().lowercase()
        if (a.isBlank() || entry.isBlank()) return
        val root = try { JSONObject(prefs(c).getString(store, "{}")!!) } catch (_: Exception) { JSONObject() }
        val appObj = root.optJSONObject(a) ?: JSONObject()
        val cur = appObj.optJSONObject(entry) ?: JSONObject().put("n", 0).put("m", 0.0)
        val n = cur.optInt("n", 0)
        val avg = cur.optDouble("m", 0.0)
        cur.put("n", n + 1).put("m", (avg * n + m) / (n + 1))   // running average of M
        appObj.put(entry, cur)
        // Cap entries per app: evict the LEAST-evidence (lowest count) key so a proven one survives.
        if (appObj.length() > MAX_OP_KEYS) {
            var dropKey: String? = null; var dropN = Int.MAX_VALUE
            val it = appObj.keys()
            while (it.hasNext()) { val k = it.next(); val kn = appObj.optJSONObject(k)?.optInt("n") ?: 0; if (kn < dropN) { dropN = kn; dropKey = k } }
            dropKey?.let { appObj.remove(it) }
        }
        root.put(a, appObj)
        if (root.length() > MAX_OP_APPS) root.keys().asSequence().firstOrNull { it != a }?.let(root::remove)
        prefs(c).edit().putString(store, root.toString()).apply()
    }

    /** The single best PROVEN transition for this app (seen >=2 with a positive average M), as a
     *  surfaced recall line for the selection prompt ("after PLAN, CRITIC paid off here"). Recall the
     *  model READS and may ignore, never a rule (docs/OPERATOR_LAYER.md V7). "" when nothing qualifies. */
    @Synchronized
    fun topTransitionFor(c: Context, app: String): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        val appObj = try { JSONObject(prefs(c).getString(OP_TRANS, "{}")!!).optJSONObject(a) } catch (_: Exception) { null } ?: return ""
        var bestKey = ""; var bestM = 0.0; var bestN = 0
        val it = appObj.keys()
        while (it.hasNext()) {
            val k = it.next(); val o = appObj.optJSONObject(k) ?: continue
            val n = o.optInt("n"); val mm = o.optDouble("m")
            if (n >= 2 && mm > 0 && (mm > bestM || (mm == bestM && n > bestN))) { bestKey = k; bestM = mm; bestN = n }
        }
        val parts = bestKey.split(">")
        if (parts.size != 2) return ""
        return "WORKED HERE BEFORE: after ${parts[0]}, ${parts[1]} paid off (avg M ${String.format("%+.1f", bestM)} over ${bestN}x) - consider it, but you decide."
    }

    /** A-3: the single WORST transition for this app (seen >=2 with a NEGATIVE average M) - a surfaced
     *  CAUTION, the mirror of topTransitionFor. The ReasoningBank finding: failure traces are the most
     *  transferable signal, and creditTransition already stores negative-M edges - they just had no reader.
     *  Recall the model READS and may ignore, never a rule (§2/V7). "" when nothing qualifies. */
    @Synchronized
    fun worstTransitionFor(c: Context, app: String): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        val appObj = try { JSONObject(prefs(c).getString(OP_TRANS, "{}")!!).optJSONObject(a) } catch (_: Exception) { null } ?: return ""
        var worstKey = ""; var worstM = 0.0; var worstN = 0
        val it = appObj.keys()
        while (it.hasNext()) {
            val k = it.next(); val o = appObj.optJSONObject(k) ?: continue
            val n = o.optInt("n"); val mm = o.optDouble("m")
            if (n >= 2 && mm < 0 && (mm < worstM || (mm == worstM && n > worstN))) { worstKey = k; worstM = mm; worstN = n }
        }
        val parts = worstKey.split(">")
        if (parts.size != 2) return ""
        return "HURT HERE BEFORE: after ${parts[0]}, ${parts[1]} went nowhere (avg M ${String.format("%+.1f", worstM)} over ${worstN}x) - a different move may be better."
    }

    /** The single best PROVEN operator for this app (chosen >=2 with a positive average M), as a surfaced
     *  recall line for the selection prompt. Reads OP_CREDIT — the per-op value V(op), populated every step
     *  by creditOperator but until now NEVER read. Recall the model READS and may ignore, never a rule
     *  (docs/OPERATOR_LAYER.md V7 — the frontier's "surface, don't argmax"). "" when nothing qualifies. */
    @Synchronized
    fun topOperatorFor(c: Context, app: String): String {
        val a = app.trim().lowercase(); if (a.isBlank()) return ""
        val appObj = try { JSONObject(prefs(c).getString(OP_CREDIT, "{}")!!).optJSONObject(a) } catch (_: Exception) { null } ?: return ""
        var bestKey = ""; var bestM = 0.0; var bestN = 0
        val it = appObj.keys()
        while (it.hasNext()) {
            val k = it.next(); val o = appObj.optJSONObject(k) ?: continue
            if (k.uppercase() in ReasoningOperators.COMPOSITE_NAMES) continue   // pyramid weights aren't pickable leaves
            val n = o.optInt("n"); val mm = o.optDouble("m")
            if (n >= 2 && mm > 0 && (mm > bestM || (mm == bestM && n > bestN))) { bestKey = k; bestM = mm; bestN = n }
        }
        if (bestKey.isBlank()) return ""
        return "HELPED HERE BEFORE: $bestKey paid off (avg M ${String.format("%+.1f", bestM)} over ${bestN}x) - consider it, but you decide."
    }

    /** W1: the set of operator names PROVEN in this app (chosen >=2 with a positive average M), read from
     *  OP_CREDIT V(op). Used only to RANK/surface the selection menu (relevantMenu) - a memory surface, the
     *  model still picks. Same proven test as topOperatorFor; returns UPPERCASE names ("" app => empty). */
    @Synchronized
    fun provenOperatorNames(c: Context, app: String): Set<String> {
        val a = app.trim().lowercase(); if (a.isBlank()) return emptySet()
        val appObj = try { JSONObject(prefs(c).getString(OP_CREDIT, "{}")!!).optJSONObject(a) } catch (_: Exception) { null } ?: return emptySet()
        val out = HashSet<String>()
        val it = appObj.keys()
        while (it.hasNext()) {
            val k = it.next(); val o = appObj.optJSONObject(k) ?: continue
            if (k.uppercase() in ReasoningOperators.COMPOSITE_NAMES) continue   // pyramid weights aren't pickable leaves
            if (o.optInt("n") >= 2 && o.optDouble("m") > 0) out.add(k.uppercase())
        }
        return out
    }

    /** REASONING CACHE: save the model-chosen operator SEQUENCE that completed a task, keyed to the
     *  objective name (newest wins, like a success playbook). Only non-DIRECT model choices. */
    @Synchronized
    fun saveReasoningPlaybook(c: Context, objectiveName: String, ops: List<String>) {
        val name = objectiveName.replace("\n", " ").trim().take(60)
        val seq = ops.filter { it.isNotBlank() && !it.equals("DIRECT", ignoreCase = true) }.joinToString(",")
        if (name.length < 4 || seq.isBlank()) return
        val arr = try { JSONArray(prefs(c).getString(OP_SEQ, "[]")) } catch (_: Exception) { JSONArray() }
        val out = JSONArray()
        for (i in 0 until arr.length()) { val o = arr.optJSONObject(i) ?: continue; if (!o.optString("name").equals(name, ignoreCase = true)) out.put(o) }
        out.put(JSONObject().put("name", name).put("seq", seq).put("time", System.currentTimeMillis()))
        while (out.length() > MAX_OP_SEQ) out.remove(0)
        prefs(c).edit().putString(OP_SEQ, out.toString()).apply()
    }

    /** The cached operator SEQUENCE most relevant to [objective] (token overlap on the saved name), or
     *  "" if none - surfaced in makePlan as a HOW-TO-THINK guide (never steps to type). */
    @Synchronized
    fun reasoningSeqFor(c: Context, objective: String): String {
        val want = tokens(objective)
        if (want.isEmpty()) return ""
        val arr = try { JSONArray(prefs(c).getString(OP_SEQ, "[]")) } catch (_: Exception) { return "" }
        var best = ""; var bestScore = 0
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val s = scoreOverlap(want, tokens(o.optString("name")))
            if (s > bestScore) { bestScore = s; best = o.optString("seq") }
        }
        return if (bestScore > 0) best else ""
    }

    // --- prompt context --------------------------------------------------------

    /** Compact block of what the agent knows, for the action prompt (empty if nothing). */
    @Synchronized
    fun forPrompt(c: Context): String {
        val f = facts(c)
        val sb = StringBuilder()
        sb.append(identityLine(c)).append('\n')   // who you are + that you persist across sessions
        deviceProfileLine(c).let { if (it.isNotBlank()) sb.append(it).append('\n') }
        if (f.length() > 0) {
            val facts = f.keys().asSequence().map { "$it = ${f.optString(it)}" }.toList()
            if (facts.isNotEmpty()) sb.append("Known facts: ").append(facts.joinToString("; ")).append('\n')
        }
        val ls = lessons(c)
        if (ls.isNotEmpty()) {
            sb.append("Lessons from experience:\n")
            ls.takeLast(12).forEach { sb.append("- ").append(it).append('\n') }
        }
        return sb.toString().trim()
    }

    /** Goal-aware variant: facts + device profile + the lessons RELEVANT to [goal] (pulled when
     *  they apply, instead of dumping the last-N). Used in the action loop where we know the task. */
    @Synchronized
    fun forPrompt(c: Context, goal: String): String {
        val f = facts(c)
        val sb = StringBuilder()
        sb.append(identityLine(c)).append('\n')   // who you are + that you persist across sessions
        deviceProfileLine(c).let { if (it.isNotBlank()) sb.append(it).append('\n') }
        if (f.length() > 0) {
            val facts = f.keys().asSequence().map { "$it = ${f.optString(it)}" }.toList()
            if (facts.isNotEmpty()) sb.append("Known facts: ").append(facts.joinToString("; ")).append('\n')
        }
        val ls = lessonsFor(c, goal, 8)
        if (ls.isNotEmpty()) {
            sb.append("Lessons that may apply here:\n")
            ls.forEach { sb.append("- ").append(it).append('\n') }
        }
        return sb.toString().trim()
    }
}
