package com.local.deviceagent

import android.content.Context
import java.io.File

/**
 * THE AGENT SANDBOX (owner 07-12: "the agent needs its own sandbox, operators like having those to test stuff as
 * needed"). A bounded, side-effect-FREE scratch space an operator invokes MID-DECISION to TEST a candidate BEFORE the
 * agent commits a real action — the runtime form of what the labs are for the developing model.
 *
 * HARD BOUNDARY (§2 + §3): the sandbox NEVER calls the accessibility executor (`performActionJson`) and never edits
 * weights. Its output is a PREDICTION / PREVIEW the agent READS — never an executed action — so it cannot smuggle a
 * world action (§3) and the model still elects the real move (§2). Every trial is ephemeral and logged `[sandbox]`.
 *
 * Three trial kinds, each reusing a built primitive as a NO-OP:
 *  - probe(hypo)   : freeGenerate on a hypothetical — "if the field held X, what next?" (CRITIC/RESOLVE test a candidate)
 *  - predict(a,scr): freeGenerate a next-screen prediction for action a WITHOUT doing it (CAUSE/PREMORTEM/DOUBT dry-run)
 *  - compute(expr) : a tiny safe arithmetic evaluator, no code-exec (PROVE/PROGRESS compute a value, never assert it)
 */
object Sandbox {

    /** PROBE — preview what the agent would emit on a hypothetical, without acting. Decode-capped, greedy (reproducible). */
    fun probe(brain: AgentBrain, hypothetical: String): String {
        val sigma = "Preview only. Given the hypothetical, emit the one action you WOULD take, as JSON. Do not act.\nexample | Messages, field id5 empty → {\"action\":\"set_text\",\"id\":5,\"value\":\"...\"}"
        val out = (try { brain.freeGenerate(sigma, hypothetical, "", greedy = true, timeoutSec = 30, capTokens = 96) } catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
        AgentLog.log("sandbox", "probe: \"${hypothetical.take(60)}\" → ${out.replace("\n", " ").take(120)}")
        return out
    }

    /** PREDICT — SINGLE-STEP veto only (survey correction 07-12): "does this ONE action plausibly move toward the goal
     *  from this screen?" NOT a multi-step rollout — no ≤8B model is an accurate multi-step text world model (Wang 2024;
     *  compounding error unsolved), so the supported use is one-step candidate-action vetoing (WebDreamer/WMA), never
     *  planning ahead. A preview decode; the action is NOT executed. */
    fun predict(brain: AgentBrain, action: String, screenDigest: String): String {
        val sigma = "One-step check only. Given this screen, this goal, and ONE candidate action: does that action plausibly move toward the goal? Answer OK or RISK:<the one concrete reason it doesn't> — one line. Do NOT plan ahead; do not act."
        val out = (try { brain.freeGenerate(sigma, "screen: ${screenDigest.take(300)}\ncandidate action: ${action.take(120)}", "", greedy = true, timeoutSec = 30, capTokens = 48) } catch (t: Throwable) { "«error: ${t.message}»" }) ?: "«null/timeout»"
        AgentLog.log("sandbox", "predict(1-step veto): $action → ${out.replace("\n", " ").take(120)}")
        return out
    }

    /** COMPUTE — the agent's exact-math scratch. For an integer a*b / a+b it ADDRESSES A FABRICATED pfc GATE-CIRCUIT
     *  (mul32/add32, byte-exact, on-device, exact even beyond Double's 2^53 range) — the fusion opening: the model's
     *  exact-compute organ is baked gates, not a guess and not host code (§3-safe: PfcEval only ripples a stored netlist).
     *  Falls back to the safe two-pass Double evaluator for decimals / longer expressions. */
    fun compute(ctx: Context, expr: String): String {
        pfcInt(ctx, expr)?.let { return it }
        val r = try { eval(expr) } catch (_: Throwable) { null }
        val s = if (r == null) "«not a plain arithmetic expression»" else fmt(r)
        AgentLog.log("sandbox", "compute: ${expr.take(60)} = $s")
        return s
    }

    /** The fabricated-circuit path: `A * B` or `A + B` on 32-bit unsigned integers → the baked mul32/add32 circuit,
     *  evaluated on-device by PfcEval. Returns null (fall back to Double) if it isn't a clean int op or the circuit
     *  isn't staged. This is what makes the agent's exact math a pfc computation it ADDRESSES. */
    private fun pfcInt(ctx: Context, expr: String): String? {
        val m = Regex("^\\s*(\\d{1,10})\\s*([*+])\\s*(\\d{1,10})\\s*$")
            .find(expr.replace(",", "").replace("×", "*")) ?: return null
        val a = m.groupValues[1].toLongOrNull() ?: return null
        val b = m.groupValues[3].toLongOrNull() ?: return null
        if (a >= (1L shl 32) || b >= (1L shl 32)) return null                 // circuit width guard
        val name = if (m.groupValues[2] == "*") "mul32" else "add32"
        val circ = PfcEval.parseFile(File(ctx.filesDir, "$name.pfc").path) ?: return null
        val w = circ.nIn / 2
        val out = PfcEval.eval(circ, PfcEval.packOperands(a to w, b to w))
        val r = PfcEval.toLong(out)
        AgentLog.log("sandbox", "compute(pfc $name gate-circuit): $a ${m.groupValues[2]} $b = $r  (byte-exact, on-device)")
        return r.toString()
    }

    // ── a minimal, safe two-pass evaluator (× ÷ then + −); tokens are ONLY numbers and + - * / (aliases × ÷) ──
    private fun eval(raw: String): Double? {
        val e = raw.replace("×", "*").replace("÷", "/").replace(",", "").trim()
        val toks = Regex("\\d*\\.?\\d+|[-+*/]").findAll(e).map { it.value }.toList()
        if (toks.isEmpty()) return null
        // reject anything that isn't a clean number/operator sequence
        if (toks.joinToString("").replace(Regex("[-+*/.]"), "").any { !it.isDigit() }) return null
        val nums = ArrayList<Double>(); val ops = ArrayList<Char>()
        var i = 0
        // first token must be a number (unary minus handled by treating a leading '-' as 0 - x)
        if (toks[0] == "-") { nums.add(0.0); ops.add('-'); i = 1 }
        while (i < toks.size) {
            nums.add(toks[i].toDoubleOrNull() ?: return null); i++
            if (i < toks.size) { ops.add(toks[i][0]); i++ }
        }
        if (nums.size != ops.size + 1) return null
        // pass 1: * and /
        var j = 0
        while (j < ops.size) {
            if (ops[j] == '*' || ops[j] == '/') {
                val a = nums[j]; val b = nums[j + 1]
                val v = if (ops[j] == '*') a * b else { if (b == 0.0) return null; a / b }
                nums[j] = v; nums.removeAt(j + 1); ops.removeAt(j)
            } else j++
        }
        // pass 2: + and -
        var acc = nums[0]
        for (k in ops.indices) acc = if (ops[k] == '+') acc + nums[k + 1] else acc - nums[k + 1]
        return acc
    }
    private fun fmt(d: Double): String = if (d == d.toLong().toDouble()) d.toLong().toString() else String.format("%.4f", d).trimEnd('0').trimEnd('.')
}
