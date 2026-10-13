package com.local.deviceagent

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Readable log viewer. A straight scrollable list of lines (theme-default colours so it's always
 * legible), with robust filtering: pick a single task, pick a tag, an "errors only" toggle, and a
 * search box that supports multiple terms (all must match) and -exclusions. A status line shows
 * how many lines match and how big the on-disk log is.
 */
class DebugLogActivity : AppCompatActivity() {

    companion object {
        // Optional extra: open the log already filtered to the task whose objective contains this.
        const val EXTRA_TASK_QUERY = "task_query"
        // Optional extra: open with this tag preselected (e.g. "think" for the one-tap thought view).
        const val EXTRA_TAG = "tag"
    }

    private lateinit var logView: TextView
    private lateinit var search: EditText
    private lateinit var taskPicker: Spinner
    private lateinit var tagPicker: Spinner
    private lateinit var status: TextView
    private lateinit var scroll: ScrollView
    private lateinit var errorsBtn: Button
    private lateinit var oldBuildsBtn: Button
    private var errorsOnly = false
    private var showOldBuilds = false
    // Archived past-build lines are read from disk ONCE (here) so render()-per-keystroke stays in memory.
    private var oldLinesCache: List<String> = emptyList()
    private var pendingTaskQuery: String? = null
    private var pendingTag: String? = null

    // Per-task segments parsed from the boundary markers: label -> lines.
    private var tasks: List<Pair<String, List<String>>> = emptyList()
    private var tagList: List<String> = emptyList()

    private val errorKeys = listOf("failed", "error", "exception", "blocked", "refused", "could not", "unavailable", "denied")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Debug log"
        pendingTaskQuery = intent.getStringExtra(EXTRA_TASK_QUERY)?.takeIf { it.isNotBlank() }
        pendingTag = intent.getStringExtra(EXTRA_TAG)?.takeIf { it.isNotBlank() }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 16)
        }

        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        buttons.addView(Button(this).apply { text = "Refresh"; setOnClickListener { reload() } })
        buttons.addView(Button(this).apply {
            text = "Copy"
            setOnClickListener {
                val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                cm.setPrimaryClip(android.content.ClipData.newPlainText("agent log", logView.text))
                Toast.makeText(this@DebugLogActivity, "Copied", Toast.LENGTH_SHORT).show()
            }
        })
        buttons.addView(Button(this).apply { text = "Share"; setOnClickListener { shareLog() } })
        buttons.addView(Button(this).apply { text = "Bundle"; setOnClickListener { exportBundle() } })
        buttons.addView(Button(this).apply { text = "Clear"; setOnClickListener { AgentLog.clear(); reload() } })
        root.addView(buttons)

        // Row 2: task scope, tag filter, and an errors-only toggle.
        val filters = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        taskPicker = Spinner(this).apply { onItemSelectedListener = selectListener() }
        tagPicker = Spinner(this).apply { onItemSelectedListener = selectListener() }
        errorsBtn = Button(this).apply {
            text = "Errors: off"
            setOnClickListener {
                errorsOnly = !errorsOnly
                text = if (errorsOnly) "Errors: ON" else "Errors: off"
                render(false)
            }
        }
        // Old-build toggle: the current build's log is shown by default (so stale behavior never
        // confuses things), but archived past-build logs hold valuable data the owner wants on demand.
        oldBuildsBtn = Button(this).apply {
            text = "Old builds: off"
            setOnClickListener {
                showOldBuilds = !showOldBuilds
                text = if (showOldBuilds) "Old builds: ON" else "Old builds: off"
                reload()
            }
        }
        filters.addView(taskPicker, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        filters.addView(tagPicker, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        filters.addView(errorsBtn)
        filters.addView(oldBuildsBtn)
        root.addView(filters)

        search = EditText(this).apply {
            hint = "Search…  (space = AND, -word = exclude)"
            setSingleLine()
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) = render(false)
                override fun beforeTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
                override fun onTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
            })
        }
        root.addView(search)

        status = TextView(this).apply {
            textSize = 11f
            setTextColor(0xFF888888.toInt())
            setPadding(0, 8, 0, 0)
        }
        root.addView(status)

        scroll = ScrollView(this)
        logView = TextView(this).apply {
            textSize = 12f
            setTextIsSelectable(true)   // selectable, theme-default colour = always readable
            setPadding(0, 16, 0, 0)
        }
        scroll.addView(logView)
        root.addView(scroll)

        setContentView(root)
        reload()
    }

    override fun onResume() { super.onResume(); reload() }

    private fun selectListener() = object : android.widget.AdapterView.OnItemSelectedListener {
        override fun onItemSelected(p: android.widget.AdapterView<*>?, v: View?, pos: Int, id: Long) = render(false)
        override fun onNothingSelected(p: android.widget.AdapterView<*>?) {}
    }

    /** The lines the viewer works over: current build, plus archived past builds when toggled on
     *  (older first, so the newest activity stays at the bottom where the view scrolls to). The
     *  archived lines are cached (read from disk once) so per-keystroke render() stays in memory. */
    private fun baseLines(): List<String> =
        if (showOldBuilds) oldLinesCache + AgentLog.snapshot() else AgentLog.snapshot()

    private fun reload() {
        oldLinesCache = if (showOldBuilds) AgentLog.oldBuildLines(this) else emptyList()
        val all = baseLines()
        tasks = parseTasks(all)
        val taskLabels = mutableListOf("All tasks")
        taskLabels.addAll(tasks.asReversed().map { it.first }) // newest first
        val keepTask = taskPicker.selectedItemPosition.takeIf { it in taskLabels.indices } ?: 0
        taskPicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, taskLabels)
        // Deep-link from the Task log: preselect the task whose label matches the objective.
        val q = pendingTaskQuery
        if (q != null) {
            pendingTaskQuery = null
            val key = q.take(28)
            val hit = taskLabels.indexOfFirst { it.contains(key, ignoreCase = true) }
            taskPicker.setSelection(if (hit >= 0) hit else keepTask)
        } else {
            taskPicker.setSelection(keepTask)
        }

        tagList = AgentLog.tags()
        val tagLabels = mutableListOf("All tags"); tagLabels.addAll(tagList)
        val keepTag = tagPicker.selectedItemPosition.takeIf { it in tagLabels.indices } ?: 0
        tagPicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, tagLabels)
        // Deep-link tag preselect (the one-tap thought view). If the tag never got logged (e.g. a
        // run with no [think] lines) fall back to searching it, so the viewer still says "nothing"
        // honestly instead of silently showing everything.
        val t = pendingTag
        if (t != null) {
            pendingTag = null
            val hit = tagList.indexOfFirst { it.equals(t, ignoreCase = true) }
            if (hit >= 0) tagPicker.setSelection(hit + 1) else search.setText("[$t]")
        } else {
            tagPicker.setSelection(keepTag)
        }

        render(true) // fresh data: jump to the latest lines
    }

    /** Split the flat line list into per-task segments using the boundary marker. */
    private fun parseTasks(lines: List<String>): List<Pair<String, List<String>>> {
        val out = mutableListOf<Pair<String, MutableList<String>>>()
        for (line in lines) {
            if (line.contains(AgentLog.TASK_MARK)) {
                val label = "${line.take(14).trim()} · " +
                    line.substringAfter(AgentLog.TASK_MARK).trim().take(40).ifBlank { "(task)" }
                out.add(label to mutableListOf(line))
            } else if (out.isEmpty()) {
                out.add("(startup)" to mutableListOf(line))
            } else out.last().second.add(line)
        }
        return out.map { it.first to it.second.toList() }
    }

    private fun scopedLines(): List<String> {
        val pos = taskPicker.selectedItemPosition
        if (pos <= 0) return baseLines() // All tasks
        return tasks.getOrNull(tasks.size - pos)?.second ?: baseLines()
    }

    private fun render(scrollToEnd: Boolean = false) {
        val total = baseLines().size
        var lines = scopedLines()

        // Tag filter.
        val tagPos = tagPicker.selectedItemPosition
        if (tagPos > 0 && tagPos - 1 in tagList.indices) {
            val tag = "[${tagList[tagPos - 1]}]"
            lines = lines.filter { it.contains(tag) }
        }

        // Errors only.
        if (errorsOnly) lines = lines.filter { l -> errorKeys.any { l.contains(it, ignoreCase = true) } }

        // Search: every plain term must be present; -term excludes.
        val terms = search.text.toString().trim().split(Regex("\\s+")).filter { it.isNotBlank() }
        if (terms.isNotEmpty()) lines = lines.filter { matches(it, terms) }

        logView.text = if (lines.isEmpty()) "(no matching lines)" else lines.joinToString("\n")
        status.text = "showing ${lines.size} of $total lines · log ${AgentLog.fileBytes() / 1024} KB"
        if (scrollToEnd) scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun matches(line: String, terms: List<String>): Boolean {
        for (t in terms) {
            if (t.length > 1 && t.startsWith("-")) {
                if (line.contains(t.substring(1), ignoreCase = true)) return false
            } else if (!line.contains(t, ignoreCase = true)) return false
        }
        return true
    }

    private fun shareLog() {
        val f = AgentLog.file()
        if (f == null || !f.exists()) { Toast.makeText(this, "No log file yet", Toast.LENGTH_SHORT).show(); return }
        try {
            val uri = androidx.core.content.FileProvider.getUriForFile(this, "$packageName.fileprovider", f)
            startActivity(android.content.Intent.createChooser(
                android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(android.content.Intent.EXTRA_STREAM, uri)
                    addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }, "Share agent log"))
        } catch (e: Exception) {
            Toast.makeText(this, "Share failed: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    /** DEBUG MODE: zip the full rich bundle (per-step prompts + raw outputs + screenshots + the tag log) and
     *  share it — the one-tap "give me everything" export. The same bundle is also pullable via
     *  `adb pull ${DebugCapture.path()}` on a dedicated debug device. */
    private fun exportBundle() {
        val z = DebugCapture.exportZip(this)
        if (z == null) {
            Toast.makeText(this, "No debug bundle yet — turn on Debug mode (Settings) and run a task.", Toast.LENGTH_LONG).show()
            return
        }
        try {
            val uri = androidx.core.content.FileProvider.getUriForFile(this, "$packageName.fileprovider", z)
            startActivity(android.content.Intent.createChooser(
                android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                    type = "application/zip"
                    putExtra(android.content.Intent.EXTRA_STREAM, uri)
                    addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }, "Export debug bundle"))
        } catch (e: Exception) {
            Toast.makeText(this, "Bundle saved at ${DebugCapture.path(this)} (share failed: ${e.message})", Toast.LENGTH_LONG).show()
        }
    }
}
