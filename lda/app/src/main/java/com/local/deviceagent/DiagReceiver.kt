package com.local.deviceagent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * adb-triggerable diagnostic + settings toggle (07-11/12, owner: "one test button… something you can use easily
 * from your end too", then the REGRESSION-MAP A/B).
 *
 *   Run the full read-only diagnostic dump ([diag] block):
 *     adb shell am broadcast -a com.local.deviceagent.DIAG -n com.local.deviceagent/.DiagReceiver
 *   Flip an A/B feature flag (regression bisect — thinking mode, etc.):
 *     adb shell am broadcast -a com.local.deviceagent.DIAG -n com.local.deviceagent/.DiagReceiver --es setflag thinking_logs --ez val false
 *   (add -f 0x20 right after a reinstall, while the app is still in Android's "stopped" state)
 *
 * The explicit `-n <component>` is REQUIRED: since Android 8, an implicit (action-only) broadcast is NOT delivered to a
 * manifest-declared receiver.
 *
 * The diagnostic is available in every build. SETFLAG accepts any SharedPreferences boolean key so the
 * receiver does not maintain a second allowlist over app capabilities.
 */
class DiagReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        // Settings toggle path: `--es setflag <name> --ez val <true|false>`.
        val setflag = intent?.getStringExtra("setflag")
        if (!setflag.isNullOrBlank()) {
            val v = intent.getBooleanExtra("val", true)
            try {
                // Same SharedPreferences SettingsManager reads (in-process cache is shared, so the next decode sees it).
                context.getSharedPreferences("agent_settings", Context.MODE_PRIVATE).edit().putBoolean(setflag, v).apply()
                AgentLog.log("diag", "SETFLAG $setflag = $v (A/B via adb)")
            } catch (t: Throwable) { AgentLog.log("diag", "SETFLAG error: ${t.message}") }
            return
        }

        // COO — CONTINUOUS OPERATOR OBSERVATORY controls (07-12): free-generation operator instrument, dumped to [obs].
        //   Start:  --es obs on            (optionally --ei obs_secs 180, --es obs_op ACCURACY, --es obs_var "battery 40%")
        //   Steer live (while running):    --es obs_op ACCURACY | --es obs_op none | --es obs_var "..." | --es obs_mode trajectory | --es obs_sampler greedy
        //   Paired A/B (v3):               --es obs_ab "none,SCHEMA"  → both arms per iteration on the same input, one atomic diff line ("" clears)
        //   Decode cap (v3):               --ei obs_cap 256           → bound each generation (0 = phase default)
        //   Stop:   --es obs off
        // §3-safe: routes only to read-only free-generation; no task, no phone driving, no account access.
        val obs = intent?.getStringExtra("obs")
        val obsOp = intent?.getStringExtra("obs_op")
        val obsVar = intent?.getStringExtra("obs_var")
        val obsMode = intent?.getStringExtra("obs_mode")
        val obsSampler = intent?.getStringExtra("obs_sampler")
        val obsSigma = intent?.getStringExtra("obs_sigma")   // RAW σ text — test any operator with no rebuild
        val obsAb = intent?.getStringExtra("obs_ab")         // v3 paired A/B "OP1,OP2" ("" clears)
        val obsCap = intent?.getIntExtra("obs_cap", -1) ?: -1 // v3 decode cap (0 = phase default; absent = -1 = leave as-is)
        if (!obs.isNullOrBlank() || obsOp != null || obsVar != null || obsMode != null || obsSampler != null || obsSigma != null || obsAb != null || obsCap >= 0) {
            val svc = AgentService.instance
            if (svc == null) { AgentLog.log("obs", "agent not running — start it first"); return }
            obsOp?.let { svc.setObsOp(it) }
            obsVar?.let { svc.setObsVar(it) }
            obsMode?.let { svc.setObsMode(it.equals("trajectory", true)) }
            obsSampler?.let { svc.setObsSampler(it.equals("greedy", true)) }
            if (obsCap >= 0) svc.setObsCap(obsCap)
            obsAb?.let { svc.setObsAb(it) }
            obsSigma?.let { svc.setObsSigma(it) }   // applied LAST so a raw σ wins if obs_op is passed in the same broadcast
            when (obs?.lowercase()) {
                "on", "start" -> svc.startObsLoop(intent?.getIntExtra("obs_secs", 180) ?: 180)
                "off", "stop" -> svc.stopObsLoop()
                null, "" -> {}   // a live setting change only (op/var/mode/sampler) — no start/stop
                else -> AgentLog.log("obs", "unknown obs command '$obs' (use on/off)")
            }
            return
        }

        // THE LAB SUITE (07-12): characterization protocols — `--es obs_lab "<protocol> [args]"`. Threaded (each decodes
        // for minutes). §3-safe: pure generation into [obs]; no task, no phone driving, no account access.
        //   sweep                    — spectrometer: constant card × every operator, ranked Δ table
        //   compose OP1,OP2          — 4 arms none/σ1/σ2/σ1‖σ2: intersection vs interference
        //   dilute [OP]              — σ+probe fixed, grow interposed filler → the binding-vs-context curve
        //   dose OP                  — σ at 100/75/50/25%/tag → the re-entry-cue curve (residency floor)
        //   persist OP               — establish→drop σ→hold→cue: the R2 trajectory-lifetime curve
        //   find OP [--es obs_target "<answer>"] — MVG search: viable answer → candidate patterns → test on a 2nd card → MVG + clusters
        //   perceive                 — LAB-8: one screen STATE × 4 renderings (verbose/current/typed/skeleton), σ+objective constant → the screen's operator-language form
        //   ask                      — LAB-9: interrogate the model IN ITS DIALECT on operator design (revealed form it generates + stated A/B, every claim VERIFIED against the measurement)
        //   minpair OP               — LAB-10: minimal-pair/commutation — hold the input constant, change ONE σ feature → contrastive (grammar) vs free (allophonic)
        //   emerge                   — LAB-11: self-talk under compression pressure (two roles, one model) → the emergent code, logged verbatim, harvested as dialect candidates (verify before ANY adoption)
        val obsLab = intent?.getStringExtra("obs_lab")
        if (!obsLab.isNullOrBlank()) {
            val svc = AgentService.instance
            if (svc == null) { AgentLog.log("obs", "agent not running — start it first"); return }
            intent?.getStringExtra("obs_target")?.let { svc.setObsTarget(it) }   // optional viable answer for LAB-7 find
            if (obsLab.trim().equals("stop", true)) svc.stopLab() else svc.runLab(obsLab)
            return
        }

        // SELF-IMPROVEMENT INTERROGATION (07-12): `--es introspect <OPERATOR|self>` → the REFINE meta-operator critiques +
        // sharpens that operator's own σ (or, for 'self', reviews the whole library), answer logged as [introspect].
        // Read-only: the model PROPOSES a sharper operator; the owner/lab decides what to adopt. Threaded (it decodes).
        val introspect = intent?.getStringExtra("introspect")
        if (!introspect.isNullOrBlank()) {
            val svc = AgentService.instance
            if (svc == null) { AgentLog.log("introspect", "agent not running — start it first"); return }
            Thread { try { svc.introspectOperator(introspect) } catch (t: Throwable) { AgentLog.log("introspect", "error: ${t.message}") } }.start()
            return
        }

        // SANDBOX (07-12): a side-effect-free scratch trial — `--es sandbox "probe <hypo>" | "compute <expr>" | "predict <action> | <screen>"`.
        val sandbox = intent?.getStringExtra("sandbox")
        if (!sandbox.isNullOrBlank()) {
            val svc = AgentService.instance
            if (svc == null) AgentLog.log("sandbox", "agent not running — start it first") else svc.runSandbox(sandbox)
            return
        }

        // CATALOG (07-12, AOS keystone): dump the agent's self-view — the browsable index of operators (with dialect
        // form + baked status), memory, exemplars, baked capabilities. Read-only perception; `--es catalog dump`.
        if (intent?.getStringExtra("catalog") != null) {
            try { AgentLog.log("catalog", "\n" + Catalog.dump(context)) } catch (t: Throwable) { AgentLog.log("catalog", "error: ${t.message}") }
            return
        }

        // SELF-FAB (owner debug, 07-24): drive/observe the self-fabricating agent loop (P1) — the agent learns a function
        // from observed I/O pairs, fabricates a circuit for it ON-DEVICE, and addresses it. §3-safe: only records pairs +
        // writes additive .pfc circuits via PfcFab; never weights, never safety, never host code.
        //   --es selffab "observe squares 5 25"   (record a pair; auto-fabricates once it recurs enough)
        //   --es selffab "ask squares 12"          (address the agent's own fabricated circuit)
        //   --es selffab "report"                  (which needs are observed / fabricated)
        val sf = intent?.getStringExtra("selffab")
        if (!sf.isNullOrBlank()) {
            try {
                val p = sf.trim().split(Regex("\\s+"))
                val fdir = context.filesDir
                when (p[0]) {
                    "observe" -> SelfFab.observe(fdir, p[1], p[2].toLong(), p[3].toLong())
                    "ask" -> {
                        val r = SelfFab.ask(fdir, p[1], p[2].toLong())
                        AgentLog.log("selffab", if (r != null) "ask ${p[1]}(${p[2]}) = $r  (addressed the agent's OWN fabricated circuit, byte-exact)"
                                                 else "ask ${p[1]}(${p[2]}): not fabricated yet")
                    }
                    "report" -> AgentLog.log("selffab", "needs: ${SelfFab.report(fdir)}")
                    else -> AgentLog.log("selffab", "unknown selffab cmd '${p[0]}' (observe|ask|report)")
                }
            } catch (t: Throwable) { AgentLog.log("selffab", "error: ${t.message}") }
            return
        }

        // PFC-EVAL (owner debug, 07-24): run a FABRICATED gate-circuit ON-DEVICE, byte-exact, and log the result — the
        // fabricated-sandbox proof (P2). `--es pfceval "mul32 987654 321321"` loads files/<name>.pfc and ripples it.
        // §3-safe: PfcEval only evaluates a STORED boolean netlist (addressed gates) — no host code, no executor, no
        // network. This is the contained exact-compute capability: the model addresses a circuit instead of guessing.
        val pfceval = intent?.getStringExtra("pfceval")
        if (!pfceval.isNullOrBlank()) {
            try {
                val parts = pfceval.trim().split(Regex("\\s+"))
                val name = parts[0]
                val f = java.io.File(context.filesDir, "$name.pfc")
                val circ = PfcEval.parseFile(f.path)
                if (circ == null) { AgentLog.log("pfceval", "circuit not found/parseable: ${f.path}"); return }
                val a = parts.getOrNull(1)?.toLongOrNull() ?: 0L
                val b = parts.getOrNull(2)?.toLongOrNull() ?: 0L
                val w = circ.nIn / 2
                val bits = PfcEval.packOperands(a to w, b to w)
                val t0 = System.nanoTime()
                val out = PfcEval.eval(circ, bits)
                val ms = (System.nanoTime() - t0) / 1e6
                val result = PfcEval.toLong(out)
                AgentLog.log("pfceval", "$name($a, $b) = $result  [${circ.nGate} gates, ${circ.nOut} out-bits, ${"%.1f".format(ms)} ms, on-device byte-exact]")
            } catch (t: Throwable) { AgentLog.log("pfceval", "error: ${t.message}") }
            return
        }

        // EXACT-COMPUTE GROUNDING self-test (owner debug, 07-24): run synthetic cases through the REAL grounding oracle
        // (ExactCompute.disagreement) and log PASS/FAIL. `--es exactground "run"`. This drives NO phone action and can
        // fire NOTHING — it only calls the pure oracle and inspects the returned note/null, so it validates the new
        // evidence-gate wiring deterministically without piloting the UI. Requires files/{mul32,add32}.pfc staged.
        val exactground = intent?.getStringExtra("exactground")
        if (!exactground.isNullOrBlank()) {
            try { AgentLog.log("exactground", ExactCompute.selfTest(context)) }
            catch (t: Throwable) { AgentLog.log("exactground", "error: ${t.message}") }
            return
        }

        // TASK TRIGGER (owner debug, 07-24: "trigger it to act… so u dont have to pilot the phone"): start a REAL agent
        // task from adb, so tasks can be driven + observed from the dev side without piloting the phone UI.
        //   adb shell am broadcast -a com.local.deviceagent.DIAG -n com.local.deviceagent/.DiagReceiver --es task "open the clock app"
        // This is the same entry the chat UI uses (ACTION_RUN_COMMAND), so the task runs through the
        // ordinary orchestrator and retains the battery/thermal floor and user Stop control.
        val task = intent?.getStringExtra("task")
        if (!task.isNullOrBlank()) {
            AgentLog.log("diag", "adb task trigger: ${task.take(160)}")
            try {
                context.startForegroundService(Intent(context, AgentService::class.java)
                    .setAction(AgentService.ACTION_RUN_COMMAND)
                    .putExtra(AgentService.EXTRA_COMMAND, task))
            } catch (t: Throwable) { AgentLog.log("diag", "task trigger error: ${t.message}") }
            return
        }

        // DIAGNOSTIC path: run the full read-only dump.
        AgentLog.log("diag", "triggered via broadcast (adb)")
        Thread {
            try { AgentService.instance?.runFullDiagnostic() ?: AgentLog.log("diag", "agent not running — start it first") }
            catch (t: Throwable) { AgentLog.log("diag", "diagnostic error: ${t.message}") }
        }.start()
    }
}
