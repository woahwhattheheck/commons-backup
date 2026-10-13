package com.local.deviceagent

import android.graphics.Typeface
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * STARTUP CALIBRATION (the owner's idea) — the loading screen that seeds the model's OPERATIONAL STATE up front
 * so it boots CALIBRATED to this owner/device, not cold. Operators serve the same purpose as training but cost
 * nothing to insert and the model sets them itself, so "calibration" is loading capability, not cosmetic priming.
 *
 * Three steps, all on-device, nothing leaves the phone:
 *  1. DEVICE self-probe — read the device tier and record it so the compute knobs match today's hardware.
 *  2. MODEL-GENERATED Q&A — the agent itself decides the few things it needs to know to serve this owner and
 *     asks them; the answers persist to memory (facts + values it can reuse).
 *  3. OPERATING-POSTURE seed — the model composes its starting operational state from the device + the answers;
 *     the orchestrator seeds the session-σ with it so the first task starts calibrated.
 *
 * Flag-gated (SettingsManager.startup_calibration, default OFF). Skippable at any point. Keyed to the model
 * fingerprint so a model swap re-calibrates.
 */
class CalibrationActivity : AppCompatActivity() {

    private lateinit var root: LinearLayout
    private val answerFields = ArrayList<Pair<String, EditText>>()   // question -> field
    private var deviceLine = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Calibrating"
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 48, 48, 64) }
        scroll.addView(root)
        setContentView(scroll)
        start()
    }

    private fun header(text: String) = root.addView(TextView(this).apply {
        this.text = text; textSize = 20f; setTypeface(typeface, Typeface.BOLD); setPadding(0, 8, 0, 16)
    })

    private fun line(text: String) = root.addView(TextView(this).apply {
        this.text = text; textSize = 14f; setPadding(0, 6, 0, 6)
    })

    private fun spinner() = root.addView(ProgressBar(this).apply { setPadding(0, 24, 0, 24) })

    private fun start() {
        header("Calibrating to you and this device…")
        // 1. DEVICE self-probe — record the tier so the compute knobs match today's hardware ("calibrate to
        //    whatever device it's on"). Pure/deterministic, no model needed.
        val settings = SettingsManager(this)
        val tier = try { DeviceStats.deviceTier(this) } catch (_: Throwable) { DeviceStats.DeviceTier.MID }
        val heavy = try { DeviceStats.modelIsHeavy(settings.getModelPath()) } catch (_: Throwable) { false }
        settings.setCalibratedTier(tier.name)
        deviceLine = "tier=${tier.name}, model=${if (heavy) "heavy" else "light"}"
        line("• Device: ${tier.name} tier — compute knobs set to match.")
        AgentLog.log("calib", "device probe: $deviceLine")

        val brain = AgentService.instance?.brainOrNull()
        if (brain == null || settings.getModelPath().isNullOrBlank()) {
            // No model to drive the Q&A / posture yet — the device half still calibrated. Mark done for the
            // current (empty) fingerprint so we don't loop, and let the owner finish.
            line("• Model not loaded yet — device calibrated; open the app with a model imported to finish.")
            finishButton("Done")
            return
        }
        AgentService.instance?.warmBrain()
        line("• Asking what I need to know to serve you…")
        val known = try { AgentMemory.forPrompt(this).take(400) } catch (_: Throwable) { "" }
        val sp = ProgressBar(this).apply { setPadding(0, 24, 0, 24) }; root.addView(sp)
        brain.generateCalibrationQuestions(deviceLine, known) { qs ->
            runOnUiThread {
                root.removeView(sp)
                if (qs.isEmpty()) {
                    line("• Nothing I need to ask — composing my operating posture…")
                    composeAndFinish("")
                } else {
                    header("A few things that would help me serve you")
                    for (q in qs) {
                        line(q)
                        val f = EditText(this).apply { hint = "your answer (optional)" }
                        answerFields.add(q to f)
                        root.addView(f)
                    }
                    finishButton("Save & calibrate")
                }
            }
        }
    }

    private fun finishButton(label: String) = root.addView(Button(this).apply {
        text = label
        setOnClickListener { onFinishTapped() }
    }).also {
        root.addView(Button(this).apply { text = "Skip"; setOnClickListener { finish() } })
    }

    private fun onFinishTapped() {
        // Persist the owner's answers to memory so the agent reuses them, and assemble a compact owner-context
        // line for the posture composition. Values are owner-set (§7); the rest are facts.
        val ctx = StringBuilder()
        for ((q, f) in answerFields) {
            val a = f.text?.toString()?.trim().orEmpty()
            if (a.isBlank()) continue
            try { AgentMemory.setFact(this, "calibration: ${q.take(60)}", a.take(200)) } catch (_: Throwable) {}
            ctx.append(q.removeSuffix("?")).append(": ").append(a).append("; ")
        }
        // Clear the fields and show a spinner while the model composes its posture.
        root.removeAllViews()
        header("Composing my operating posture…")
        spinner()
        composeAndFinish(ctx.toString().take(400))
    }

    private fun composeAndFinish(ownerContext: String) {
        val settings = SettingsManager(this)
        val brain = AgentService.instance?.brainOrNull()
        val fp = try { ModelStore.activeFingerprint(this, settings) } catch (_: Throwable) { "" }
        if (brain == null) { AgentMemory.setCalibration(this, fp, ""); finish(); return }
        brain.composeCalibrationPosture(deviceLine, ownerContext) { posture ->
            runOnUiThread {
                AgentMemory.setCalibration(this, fp, posture)
                AgentLog.log("calib", "calibrated model $fp: ${posture.take(80)}")
                root.removeAllViews()
                header("Calibrated.")
                if (posture.isNotBlank()) line("I'll start with this stance: $posture")
                line("You can re-calibrate any time from Settings.")
                finishButton("Start")
            }
        }
    }
}
