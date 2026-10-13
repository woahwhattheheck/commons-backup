package com.local.deviceagent

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * "Train me" - where the owner teaches the agent new skills. Two ways, both of which produce a
 * GENERALIZED procedure (named app + labelled elements), not a literal replay of taps:
 *
 *  1. Describe it in words ("how to send a message in the Gemini app") -> the model writes a
 *     reusable how-to it can follow itself.
 *  2. Show it once -> we record the SEMANTIC steps the owner takes (which app, which labelled
 *     button/field) and the model generalizes them into a how-to.
 *
 * It also surfaces the "things I couldn't do yet" list (tasks the agent gave up on), so the
 * owner can turn a failure into a taught skill. Skills are injected into the planner, so once
 * taught the agent does the task ITSELF.
 */
class TrainingActivity : AppCompatActivity() {

    companion object {
        // The task being demonstrated, kept across the app being backgrounded while the owner
        // performs the steps. Lives as long as the recording does (same process).
        @Volatile private var pendingGoal: String = ""
    }

    private lateinit var root: LinearLayout
    private var field: EditText? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Train the agent"
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 40, 48, 64)
        }
        scroll.addView(root)
        setContentView(scroll)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun recording(): Boolean = ActionAccessibilityService.instance?.recording == true

    private fun render() {
        root.removeAllViews()

        // When a demonstration is in progress, the owner has come back to finish it.
        if (recording()) {
            header("● Recording your demonstration")
            caption(
                if (pendingGoal.isBlank()) "Do the task in its app, then tap Finish."
                else "Showing me: “$pendingGoal”.\nDo it in its app, then tap Finish."
            )
            bigButton("Finish & learn") { finishDemo() }
            addBtn("Cancel") { cancelDemo() }
            divider()
        }

        header("Teach me something new")
        caption("Describe a task in your own words, or show me by doing it once. I learn the METHOD, so next time I do it myself — I'm not just copying your taps.")
        val f = EditText(this).apply {
            hint = "e.g. how to send a message in the Gemini app"
            setText(pendingGoal.takeUnless { recording() } ?: "")
        }
        field = f
        root.addView(f)
        addBtn("Teach by describing it") { teachByText(currentField()) }
        addBtn("Show me — record my steps") { startDemo(currentField()) }

        // INV-49 imitation read-out: how well the agent currently predicts the owner's demonstrated steps.
        // Shown only once it's on and at least one demo has been scored — a self-eval, not a control.
        if (SettingsManager(this).isImitationLearningEnabled()) {
            val fit = AgentMemory.imitationFit(this); val n = AgentMemory.imitationFitCount(this)
            if (fit >= 0) caption("Learning you: I currently predict your next step about $fit% of the time (over $n demo${if (n == 1) "" else "s"}). This rises as I learn your habits.")
        }

        header("Skills you've taught me")
        val skills = AgentMemory.skills(this)
        if (skills.isEmpty()) caption("None yet. Teach me one above.")
        else { caption("Tap a skill to see its steps or delete it."); skills.forEach { skillRow(it) } }

        header("Things I couldn't do yet")
        val unknown = AgentMemory.unknownActions(this)
        if (unknown.isEmpty()) caption("Nothing pending. This fills up when I get stuck on a task — then you can teach me.")
        else { caption("Tap one to teach it."); unknown.forEach { unknownRow(it) } }

        divider()
        addBtn("Re-scan installed apps") { rescan() }
        caption("Lets me learn what apps are on this phone so I navigate to the right one.")
    }

    private fun currentField(): String = field?.text?.toString()?.trim().orEmpty()

    // --- teach by words --------------------------------------------------------

    private fun teachByText(desc: String) {
        if (desc.length < 4) { toast("Type what you want to teach me first."); return }
        val brain = AgentService.instance?.brainOrNull()
        if (brain == null) { toast("Turn the agent on first so I can think it through."); return }
        toast("Thinking about how to do that…")
        brain.learnSkillFromText(desc) { out ->
            runOnUiThread {
                val name = if (out.isBlank()) null
                    else AgentMemory.addSkillFromModel(this@TrainingActivity, out, "described", desc)
                if (name != null) {
                    AgentMemory.removeUnknownAction(this@TrainingActivity, desc)
                    pendingGoal = ""
                    toast("Learned: $name")
                } else {
                    toast("I couldn't turn that into steps. Try describing it more concretely, or show me.")
                }
                render()
            }
        }
    }

    // --- teach by demonstration ------------------------------------------------

    private fun startDemo(goal: String) {
        val acc = ActionAccessibilityService.instance
        if (acc == null) { toast("Enable the accessibility service first (Settings)."); return }
        if (recording()) { toast("Already recording — tap Finish when you're done."); return }
        pendingGoal = goal
        acc.startDemonstration()
        Toast.makeText(this, "Recording. Do the task, then reopen Local Agent → Train → Finish.", Toast.LENGTH_LONG).show()
        // Send the owner to a clean start so they can navigate to the app and perform it.
        startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
            .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun finishDemo() {
        val acc = ActionAccessibilityService.instance ?: run { render(); return }
        val steps = acc.stopDemonstration()
        val goal = pendingGoal
        if (steps.isEmpty()) {
            toast("I didn't catch any steps that time. Try again, going a little slower.")
            render(); return
        }
        val brain = AgentService.instance?.brainOrNull()
        if (brain == null) {
            // No model loaded: keep the demonstration as a literal skill so it isn't lost.
            saveRawDemo(goal, steps)
            toast("Saved your steps. Turn the agent on later and I'll refine them into a general method.")
            render(); return
        }
        toast("Learning from what you showed me…")
        // INV-49 IMITATION (learn-from-watching): when it's on, ALSO predict how the agent WOULD have done this
        // from the goal alone and score it against what the owner actually did — the model is legitimately up
        // here (owner tapped Finish), so this predict pass is §8-safe. Updates the running "how well I model you"
        // fit and weights the steps the agent DIDN'T anticipate up in the training data (off-device recipe
        // prefers them). On-device; the durable weight change stays off-device + owner-approved. Independent of
        // the generalize call below (both use the loaded model).
        if (SettingsManager(this).isImitationLearningEnabled()) {
            brain.predictAndScoreDemo(goal, steps) { fit, missed ->
                runOnUiThread {
                    if (fit >= 0) {
                        val ema = AgentMemory.recordImitationFit(this@TrainingActivity, fit)
                        // Weight the surprising (un-anticipated) steps up in the training data, so an off-device
                        // recipe learns what the model got wrong about the owner. Gated on data-capture (that's
                        // where training data lives); the update itself is never on-device (INV-46).
                        if (SettingsManager(this@TrainingActivity).isDataCaptureEnabled()) {
                            for (s in missed.take(12)) {
                                val app = Regex("open the (.+) app").find(s)?.groupValues?.get(1)?.trim() ?: "?"
                                TrainingData.record(this@TrainingActivity, goal, app, "(owner demonstration)", s, "OWNER_DEMO_SURPRISE")
                                TrainingData.recordStepScore(this@TrainingActivity, 3, "IMITATE")   // high weight = high-value step
                            }
                        }
                        toast("I'd have predicted $fit% of that (I model you ~$ema% now).")
                    }
                }
            }
        }
        brain.generalizeDemonstration(goal, steps) { out ->
            runOnUiThread {
                val name = if (out.isBlank()) null
                    else AgentMemory.addSkillFromModel(this@TrainingActivity, out, "shown",
                        goal.ifBlank { "a task you showed me" }, raw = steps.joinToString("\n") { "- $it" })
                if (name != null) {
                    AgentMemory.removeUnknownAction(this@TrainingActivity, goal)
                    toast("Learned: $name")
                } else {
                    saveRawDemo(goal, steps)
                    toast("Saved your steps.")
                }
                pendingGoal = ""
                render()
            }
        }
    }

    private fun saveRawDemo(goal: String, steps: List<String>) {
        val name = goal.ifBlank { "a task you showed me" }
        AgentMemory.addSkill(this, name, "", steps.joinToString("\n") { "- $it" }, "shown")
        AgentMemory.removeUnknownAction(this, goal)
    }

    private fun cancelDemo() {
        ActionAccessibilityService.instance?.stopDemonstration()
        pendingGoal = ""
        toast("Training cancelled.")
        render()
    }

    private fun rescan() {
        val acc = ActionAccessibilityService.instance
        if (acc == null) { toast("Enable the accessibility service first (Settings)."); return }
        acc.scanAll()
        val n = AgentMemory.deviceApps(this).size
        toast("Scanned $n apps + your phone's profile and default apps.")
    }

    // --- rows ------------------------------------------------------------------

    private fun skillRow(skill: AgentMemory.Skill) = root.addView(TextView(this).apply {
        val tag = if (skill.source == "shown") "shown" else "described"
        text = "• ${skill.name}  ($tag)  ✎"
        textSize = 15f
        setPadding(0, 12, 0, 0)
        setOnClickListener {
            val body = (if (skill.app.isBlank()) "" else "App: ${skill.app}\n\n") +
                "WHAT I'LL DO (generalized):\n" + skill.steps +
                (if (skill.raw.isBlank()) "" else "\n\nWHAT I LEARNED IT FROM (recorded):\n" + skill.raw)
            AlertDialog.Builder(this@TrainingActivity)
                .setTitle(skill.name)
                .setMessage(body)
                .setNeutralButton("Delete") { _, _ ->
                    AgentMemory.removeSkill(this@TrainingActivity, skill.name); render()
                }
                .setPositiveButton("Close", null)
                .show()
        }
    })

    private fun unknownRow(what: String) = root.addView(TextView(this).apply {
        text = "• $what"
        textSize = 15f
        setPadding(0, 12, 0, 0)
        setOnClickListener {
            AlertDialog.Builder(this@TrainingActivity)
                .setTitle("Teach me this?")
                .setMessage(what)
                .setPositiveButton("Show me") { _, _ -> startDemo(what) }
                .setNeutralButton("Delete") { _, _ ->
                    AgentMemory.removeUnknownAction(this@TrainingActivity, what); render()
                }
                .setNegativeButton("Describe it") { _, _ ->
                    field?.setText(what); field?.requestFocus()
                    toast("Filled in above — tweak it, then tap ‘Teach by describing’.")
                }
                .show()
        }
    })

    // --- tiny view builders (match MemoryActivity's style) ---------------------

    private fun header(text: String) = root.addView(TextView(this).apply {
        this.text = text
        textSize = 18f
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, 40, 0, 6)
    })

    private fun caption(text: String) = root.addView(TextView(this).apply {
        this.text = text
        textSize = 13f
        setTextColor(0xFF888888.toInt())
        gravity = Gravity.START
        setPadding(0, 0, 0, 4)
    })

    private fun divider() = root.addView(TextView(this).apply { setPadding(0, 20, 0, 0) })

    private fun addBtn(label: String, onClick: () -> Unit) = root.addView(Button(this).apply {
        text = label
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, 12, 0, 0) }
        setOnClickListener { onClick() }
    })

    private fun bigButton(label: String, onClick: () -> Unit) = root.addView(Button(this).apply {
        text = label
        textSize = 17f
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, 16, 0, 0) }
        setOnClickListener { onClick() }
    })

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
}
