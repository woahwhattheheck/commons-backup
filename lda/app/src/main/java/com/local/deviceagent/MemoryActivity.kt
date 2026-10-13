package com.local.deviceagent

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
 * Lets the owner review exactly what the agent has stored about them and itself -
 * facts, lessons it has learned, and logins it created - and wipe it. This keeps the
 * self-learning auditable so it can't quietly drift off the rails. Read-only review +
 * a clear button; the agent writes here, the user verifies here.
 */
class MemoryActivity : AppCompatActivity() {

    private lateinit var root: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Agent memory"
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 40, 48, 64)
        }
        scroll.addView(root)
        setContentView(scroll)
        render()
    }

    private fun render() {
        root.removeAllViews()
        caption("Everything the agent remembers is here — tap any item to edit or delete it.")

        // Values come FIRST: they are the agent's character, above facts/knowledge. This is the
        // owner's "somewhere I can manually give agent values" - the top tier of its memory.
        header("Its values (what it cares about)")
        caption("The agent's character — the priors it weighs every decision against. It pursues your goals in the way that best honors them, and voices a conflict rather than silently acting against one. Values never override its safety rules or your direct command. ★ = held most deeply.")
        val values = AgentMemory.valuesDetailed(this)
        if (values.isEmpty()) caption("None yet. Add what matters to you and the agent will act by it.")
        else values.forEach { (t, w) -> editableValue(t, w) }
        addValueButton()

        // Thinking moves sit right below values: both are YOUR deliberate input the agent reasons WITH.
        // Values are who it is; thinking moves are how it may think - each joins the menu of moves the
        // model CHOOSES from each step. They are clauses, never forced actions (the §2 note below).
        header("My thinking moves")
        caption("Reasoning moves you write for the agent — a one-word NAME, when to use it, and how to think in that moment. Like values, these are choices the agent CHOOSES among (the model picks the move that fits the screen); they're never forced actions or overrides. It also invents its own per task.")
        val ops = AgentMemory.ownerOperatorsDetailed(this)
        if (ops.isEmpty()) caption("None yet. Add a way of thinking and it joins the moves the agent can pick from.")
        else ops.forEach { (n, w, d) -> editableOwnerOp(n, w, d) }
        addOwnerOpButton()

        // W2: the moves the agent INVENTED for itself and KEPT because they measurably helped (it drops the
        // ones that don't). Read-only + deletable so the owner can see and trust what it taught itself - the
        // transparency §2 wants; the agent still only CHOOSES among these, never forced.
        val invented = AgentMemory.agentOperatorsDetailed(this)
        if (invented.isNotEmpty()) {
            header("Moves it invented")
            caption("Thinking moves the agent wrote for ITSELF and kept because they measurably helped on real tasks (it prunes the ones that don't pay off). It still only picks the move that fits the screen — never forced.")
            invented.forEach { (n, w, d) ->
                val shown = if (w.isBlank()) "• $n — $d" else "• $n — $d\n   (when: $w)"
                deletableLine(shown, "Delete this invented move?") { AgentMemory.removeAgentOperator(this, n); render() }
            }
        }

        header("Facts it knows")
        val facts = AgentMemory.factsList(this)
        if (facts.isEmpty()) caption("Nothing yet. Say \"remember my … is …\".")
        else facts.forEach { (k, v) -> editableFact(k, v) }

        header("Skills you've taught it")
        val skills = AgentMemory.skills(this)
        if (skills.isEmpty()) caption("None yet. Teach it from the Train screen or the floating button.")
        else skills.forEach { editableSkill(it) }

        header("Learned from watching you")
        val obs = AgentMemory.observationsDetailed(this)
        if (obs.isEmpty()) caption("Nothing yet. Turn on “Learn from watching me” in Settings, then navigate your phone and it fills in here.")
        else { caption("Navigation it picked up by watching you use the phone."); obs.forEach { (o, goal) ->
            // Show the task it was learned under (owner: without it he couldn't judge what the
            // "advancement" was). Deletion still keys on the observation text alone.
            val shown = if (goal.isBlank()) "• $o" else "• $o\n   (during: $goal)"
            deletableLine(shown, "Forget this?") { AgentMemory.removeObservation(this, o); render() }
        } }

        header("Things it couldn't do yet")
        val unknown = AgentMemory.unknownActions(this)
        if (unknown.isEmpty()) caption("Nothing pending.")
        else unknown.forEach { what ->
            deletableLine("• $what", "Remove this?") { AgentMemory.removeUnknownAction(this, what); render() }
        }

        header("Lessons it learned")
        val lessons = AgentMemory.lessons(this)
        if (lessons.isEmpty()) caption("Nothing yet. It records tips when it gets stuck or succeeds after a struggle.")
        else lessons.forEach { editableLesson(it) }

        header("Un-learned (beliefs reality disproved)")
        val falsified = AgentMemory.falsifiedObservations(this)
        if (falsified.isEmpty()) caption("None. When a remembered step fails 3 times in real use it moves here - remembered as FALSE rather than erased, so the same wrong belief can't be quietly re-learned.")
        else falsified.forEach {
            deletableLine("✗ $it", "Forget this correction?") {
                AgentMemory.removeObservation(this, it); render()
            }
        }

        header("Mistakes it's learning from")
        val bad = AgentMemory.badMemories(this)
        if (bad.isEmpty()) caption("None. When it gets stuck it notes what went wrong + what to do instead, and avoids repeating it.")
        else bad.forEach { (m, b) ->
            deletableLine("• $m${if (b.isNotBlank()) "\n   → better: $b" else ""}", "Forget this?") {
                AgentMemory.removeBadMemory(this, m); render()
            }
        }

        header("Logins it created")
        val logins = AgentMemory.logins(this)
        if (logins.isEmpty()) caption("None. When the agent signs up for a service it records the login here.")
        else logins.forEach { editableLogin(it) }

        header("Send shortcuts it learned")
        val recipes = AgentMemory.sendRecipes(this)
        if (recipes.isEmpty()) caption("None. It records which Send method worked per app.")
        else recipes.forEach { (pkg, strat) ->
            deletableLine("• $pkg → strategy $strat", "Forget this shortcut?") { AgentMemory.removeSendRecipe(this, pkg); render() }
        }

        header("What it knows about your phone")
        val profile = AgentMemory.deviceProfile(this)
        if (profile.isBlank()) caption("Not scanned yet. Use “Re-scan installed apps” on the Train screen.")
        else caption(profile)
        val apps = AgentMemory.deviceApps(this)
        if (apps.isEmpty()) caption("Apps: not scanned yet.")
        else {
            val joined = apps.joinToString(", ")
            caption("${apps.size} apps known: ${joined.take(400)}${if (joined.length > 400) "…" else ""}")
            deletableLine("Clear scanned apps & profile", "Clear what the agent learned about your phone?") {
                AgentMemory.setDeviceApps(this, emptyList()); AgentMemory.setDeviceProfile(this, ""); render()
            }
        }

        val clear = Button(this).apply {
            text = "Clear ALL memory"
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 48, 0, 0) }
            setOnClickListener { confirmClear() }
        }
        root.addView(clear)
    }

    /** A value the owner set: tap to edit its text/strength or delete it. ★=core, •=value, ◦=mild. */
    private fun editableValue(text: String, intensity: Int) = root.addView(TextView(this).apply {
        val mark = when (intensity) { 3 -> "★"; 1 -> "◦"; else -> "•" }
        this.text = "$mark $text  ✎"
        textSize = 15f; setPadding(0, 10, 0, 0)
        setOnClickListener {
            valueDialog("Edit value", text, intensity,
                onDelete = { AgentMemory.removeValue(this@MemoryActivity, text); render() }) { nt, w ->
                // Editing replaces the old entry (clearing the text deletes it, like facts/lessons).
                AgentMemory.removeValue(this@MemoryActivity, text)
                if (nt.isNotEmpty()) AgentMemory.addValue(this@MemoryActivity, nt, w)
                render()
            }
        }
    })

    private fun addValueButton() = root.addView(Button(this).apply {
        text = "＋ Add a value"
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { setMargins(0, 12, 0, 0) }
        setOnClickListener {
            valueDialog("Add a value", "", 2) { t, w ->
                if (t.isNotEmpty()) AgentMemory.addValue(this@MemoryActivity, t, w)
                render()
            }
        }
    })

    /** Add/edit a value: a text field + a 3-way strength picker (Mild / Value / Core = intensity
     *  1/2/3, the desire-strength dial). onDelete adds a Delete button (edit only). */
    private fun valueDialog(title: String, text: String, intensity: Int,
                            onDelete: (() -> Unit)? = null, onSave: (String, Int) -> Unit) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 24, 48, 0) }
        val input = EditText(this).apply {
            setText(text); hint = "e.g. protect my privacy above convenience"; setSelection(text.length)
        }
        box.addView(input)
        val chosen = intArrayOf(intensity.coerceIn(1, 3))
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 16, 0, 0) }
        val btns = ArrayList<Button>()
        listOf("Mild", "Value", "Core").forEachIndexed { i, lbl ->
            val w = i + 1
            val b = Button(this).apply {
                this.text = lbl
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                setOnClickListener { chosen[0] = w; btns.forEachIndexed { j, bb -> Ui.styleButton(bb, primary = j + 1 == w) } }
            }
            btns.add(b); row.addView(b)
        }
        btns.forEachIndexed { j, bb -> Ui.styleButton(bb, primary = j + 1 == chosen[0]) }
        box.addView(row)
        val builder = AlertDialog.Builder(this).setTitle(title).setView(box)
            .setPositiveButton("Save") { _, _ -> onSave(input.text.toString().trim(), chosen[0]) }
            .setNegativeButton("Cancel", null)
        if (onDelete != null) builder.setNeutralButton("Delete") { _, _ -> onDelete() }
        builder.show()
    }

    /** An owner-authored thinking move: tap to edit its name/when/how or delete it. Mirrors
     *  editableValue. ◆ marks it as a reasoning move (vs ★/•/◦ for values). */
    private fun editableOwnerOp(name: String, whenTo: String, doThis: String) = root.addView(TextView(this).apply {
        this.text = "◆ $name — $whenTo  ✎"
        textSize = 15f; setPadding(0, 10, 0, 0)
        setOnClickListener {
            ownerOpDialog("Edit thinking move", name, whenTo, doThis,
                onDelete = { AgentMemory.removeOwnerOperator(this@MemoryActivity, name); render() }) { n, w, d ->
                // Editing replaces the old entry (the NAME is the key; addOwnerOperator dedups by name).
                AgentMemory.removeOwnerOperator(this@MemoryActivity, name)
                if (n.isNotEmpty() && d.isNotEmpty()) AgentMemory.addOwnerOperator(this@MemoryActivity, n, w, d)
                render()
            }
        }
    })

    private fun addOwnerOpButton() = root.addView(Button(this).apply {
        text = "＋ Add a thinking move"
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { setMargins(0, 12, 0, 0) }
        setOnClickListener {
            ownerOpDialog("Add a thinking move", "", "", "") { n, w, d ->
                if (n.isNotEmpty() && d.isNotEmpty()) AgentMemory.addOwnerOperator(this@MemoryActivity, n, w, d)
                render()
            }
        }
    })

    /** Add/edit an owner operator: THREE inputs - a one-word NAME, WHEN to use it, and HOW to think
     *  (the clause). The agent SELECTS among these; it never forces one (a clause, not an action -
     *  §2). onDelete adds a Delete button (edit only). Mirrors valueDialog. */
    private fun ownerOpDialog(title: String, name: String, whenTo: String, doThis: String,
                              onDelete: (() -> Unit)? = null, onSave: (String, String, String) -> Unit) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 24, 48, 0) }
        val nameIn = EditText(this).apply {
            setText(name); hint = "NAME (one word, e.g. SLOW)"; setSelection(name.length)
        }
        val whenIn = EditText(this).apply {
            setText(whenTo); hint = "when to use it (e.g. the screen is risky)"; setSelection(whenTo.length)
        }
        val doIn = EditText(this).apply {
            setText(doThis); hint = "how to think (e.g. re-read every field before you tap)"
            setSelection(doThis.length); minLines = 2; isSingleLine = false
        }
        box.addView(nameIn); box.addView(whenIn); box.addView(doIn)
        val builder = AlertDialog.Builder(this).setTitle(title).setView(box)
            .setPositiveButton("Save") { _, _ ->
                onSave(nameIn.text.toString().trim(), whenIn.text.toString().trim(), doIn.text.toString().trim())
            }
            .setNegativeButton("Cancel", null)
        if (onDelete != null) builder.setNeutralButton("Delete") { _, _ -> onDelete() }
        builder.show()
    }

    /** A taught skill: tap to read its steps, edit them, or delete it. */
    private fun editableSkill(skill: AgentMemory.Skill) = root.addView(TextView(this).apply {
        text = "• ${if (skill.pinned) "📌 " else ""}${skill.name}  (${skill.source})  ✎"
        textSize = 15f
        setPadding(0, 10, 0, 0)
        setOnClickListener {
            val body = (if (skill.app.isBlank()) "" else "App: ${skill.app}\n\n") +
                "WHAT I'LL DO (generalized):\n" + skill.steps +
                (if (skill.raw.isBlank()) "" else "\n\nWHAT I LEARNED IT FROM (recorded):\n" + skill.raw)
            AlertDialog.Builder(this@MemoryActivity)
                .setTitle(skill.name)
                .setMessage(body)
                .setPositiveButton("Edit steps") { _, _ ->
                    val input = EditText(this@MemoryActivity).apply {
                        setText(skill.steps); setSelection(skill.steps.length); minLines = 4; isSingleLine = false
                    }
                    AlertDialog.Builder(this@MemoryActivity)
                        .setTitle("Edit “${skill.name}”")
                        .setView(input)
                        .setPositiveButton("Save") { _, _ ->
                            val nv = input.text.toString().trim()
                            if (nv.isEmpty()) AgentMemory.removeSkill(this@MemoryActivity, skill.name)
                            else AgentMemory.addSkill(this@MemoryActivity, skill.name, skill.app, nv, skill.source)
                            render()
                        }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
                .setNeutralButton("Delete") { _, _ -> AgentMemory.removeSkill(this@MemoryActivity, skill.name); render() }
                // Pin/unpin: a pinned skill (📌) is never auto-evicted by the cap. Tap outside to close.
                .setNegativeButton(if (skill.pinned) "Unpin" else "📌 Pin") { _, _ ->
                    AgentMemory.setSkillPinned(this@MemoryActivity, skill.name, !skill.pinned); render()
                }
                .show()
        }
    })

    /** A created login: tap to edit the saved secret or delete the whole entry. */
    private fun editableLogin(login: AgentMemory.Login) = root.addView(TextView(this).apply {
        text = "• ${login.service} — ${login.username} / ${login.secret}  ✎"
        textSize = 15f
        setPadding(0, 10, 0, 0)
        setOnClickListener {
            val input = EditText(this@MemoryActivity).apply { setText(login.secret); setSelection(login.secret.length) }
            AlertDialog.Builder(this@MemoryActivity)
                .setTitle("${login.service} (${login.username})")
                .setView(input)
                .setPositiveButton("Save") { _, _ ->
                    AgentMemory.updateLoginSecret(this@MemoryActivity, login.service, login.username, login.time, input.text.toString().trim())
                    render()
                }
                .setNeutralButton("Delete") { _, _ ->
                    AgentMemory.removeLogin(this@MemoryActivity, login.service, login.username, login.time); render()
                }
                .setNegativeButton("Cancel", null)
                .show()
        }
    })

    /** A line the owner can tap to delete (with a confirm). */
    private fun deletableLine(text: String, confirm: String, onDelete: () -> Unit) = root.addView(TextView(this).apply {
        this.text = text
        textSize = 15f
        setPadding(0, 10, 0, 0)
        setOnClickListener {
            AlertDialog.Builder(this@MemoryActivity)
                .setMessage(confirm)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Delete") { _, _ -> onDelete() }
                .show()
        }
    })

    private fun confirmClear() {
        AlertDialog.Builder(this)
            .setTitle("Clear all memory?")
            .setMessage("This wipes every fact, lesson, and saved login. Can't be undone.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Clear") { _, _ ->
                // FULL wipe: AgentMemory.clear() only clears AgentMemory's own prefs; the sibling ledgers
                // live in their OWN prefs/files and were silently surviving a "wipe" (RegimeKey/DreamFlywheel/
                // MechanismRouter, and the SM4 ReferenceStore supervision feed). Clear them alongside so a
                // "fresh" agent really is fresh. NOTE: the WeightGenome journal is deliberately NOT wiped here
                // — it's the reversible model-edit ledger; dropping it would orphan un-reverted weight edits.
                // The owner reverts/restores the model via its own Settings controls, not the memory wipe.
                AgentMemory.clear(this)
                RegimeKey.clear(this); DreamFlywheel.clear(this); MechanismRouter.clear(this)
                ReferenceStore.clear(this); WorldModel.clear(this)
                render()
            }
            .show()
    }

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

    private fun line(text: String) = root.addView(TextView(this).apply {
        this.text = text
        textSize = 15f
        setPadding(0, 6, 0, 0)
    })

    /** A learned lesson the owner can tap to edit (fix a slightly-off one) or delete. */
    private fun editableLesson(text: String) = root.addView(TextView(this).apply {
        this.text = "• $text  ✎"
        textSize = 15f
        setPadding(0, 10, 0, 0)
        setOnClickListener {
            val input = EditText(this@MemoryActivity).apply { setText(text); setSelection(text.length) }
            AlertDialog.Builder(this@MemoryActivity)
                .setTitle("Edit memory")
                .setView(input)
                .setPositiveButton("Save") { _, _ ->
                    val nv = input.text.toString().trim()
                    AgentMemory.removeLesson(this@MemoryActivity, text)
                    if (nv.isNotEmpty()) AgentMemory.addLesson(this@MemoryActivity, nv)
                    render()
                }
                .setNeutralButton("Delete") { _, _ -> AgentMemory.removeLesson(this@MemoryActivity, text); render() }
                .setNegativeButton("Cancel", null)
                .show()
        }
    })

    /** A stored fact the owner can tap to edit its value or delete it. */
    private fun editableFact(k: String, v: String) = root.addView(TextView(this).apply {
        this.text = "• $k = $v  ✎"
        textSize = 15f
        setPadding(0, 10, 0, 0)
        setOnClickListener {
            val input = EditText(this@MemoryActivity).apply { setText(v); setSelection(v.length) }
            AlertDialog.Builder(this@MemoryActivity)
                .setTitle("Edit \"$k\"")
                .setView(input)
                .setPositiveButton("Save") { _, _ ->
                    val nv = input.text.toString().trim()
                    if (nv.isEmpty()) AgentMemory.removeFact(this@MemoryActivity, k)
                    else AgentMemory.setFact(this@MemoryActivity, k, nv)
                    render()
                }
                .setNeutralButton("Delete") { _, _ -> AgentMemory.removeFact(this@MemoryActivity, k); render() }
                .setNegativeButton("Cancel", null)
                .show()
        }
    })
}
