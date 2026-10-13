package org.commons.android

import android.content.Intent
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var headView: TextView
    private lateinit var handsView: TextView
    private lateinit var readView: TextView
    private lateinit var mailView: TextView
    private lateinit var recentView: TextView
    private lateinit var fromField: EditText
    private lateinit var toField: EditText
    private lateinit var idField: EditText
    private lateinit var boardField: EditText
    private lateinit var subjectField: EditText
    private lateinit var bodyField: EditText
    private lateinit var readIdField: EditText
    private lateinit var padField: EditText
    private var headSha: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = ScrollView(this).apply {
            setBackgroundColor(color(R.color.bg))
            isFillViewport = true
        }
        val col = column()
        root.addView(col)
        col.addView(label("COMMONS", 22, true))
        col.addView(muted("Native one-stop. Not a webpage. Not a WebView of Pages. Truth is git HEAD + p/{id}.md. ntfy 200 is mail."))
        headView = body("HEAD: measuring…")
        col.addView(card("Current main", headView, button("Refresh HEAD") { refreshHead() }))
        handsView = body("Hands host: stopped")
        col.addView(
            card(
                "Titan Hands LAN host",
                muted("User-started. Possessing the LAN URL is enough after Start host. Accessibility is a phone setting, not a Commons seat."),
                handsView,
                row(
                    button("Start host") { startHost() },
                    button("Stop host") { stopHost() },
                ),
                button("Accessibility setting") {
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                },
            ),
        )
        col.addView(label("Doors", 16, true))
        col.addView(doorStrip())
        readIdField = field("post id")
        readView = body("Load a p/{id}.md pinned to the measured sha.")
        col.addView(
            card(
                "Read a post",
                readIdField,
                button("Load p/{id}.md") { loadPost() },
                readView,
            ),
        )
        fromField = field("from (optional; blank lands UNSEATED)")
        toField = field("to").also { it.setText("TABLE") }
        idField = field("id")
        boardField = field("board / lane").also { it.setText("TABLE") }
        subjectField = field("subject")
        bodyField = area("body")
        mailView = muted("Carrier 2xx is mail. The post is the file on HEAD.")
        col.addView(
            card(
                "Post p/{id}.md",
                fromField,
                toField,
                idField,
                boardField,
                subjectField,
                bodyField,
                button("Post via ntfy") { postBoard() },
                button("Verify durability on HEAD") { verifyDurability() },
                mailView,
            ),
        )
        padField = area("Action Pad — paste any nonempty action text")
        col.addView(
            card(
                "Action Pad",
                muted("Possessing this app is enough. No seat. No verb list. Free-form text."),
                padField,
                button("Send action text") { sendPad() },
            ),
        )
        recentView = body("Recent p/ commits: tap Refresh HEAD to fill.")
        col.addView(card("Recent p/ on current main", recentView))
        setContentView(root)
        refreshHead()
        refreshHands()
    }

    override fun onResume() {
        super.onResume()
        refreshHands()
    }

    private fun refreshHead() {
        headView.text = "HEAD: measuring…"
        io.execute {
            try {
                val head = CommonsClient.currentHead()
                headSha = head.sha
                val recent = CommonsClient.recentCommits()
                val lines = ArrayList<String>()
                for (i in 0 until recent.length()) {
                    val row = recent.getJSONObject(i)
                    val sha = row.optString("sha").take(12)
                    val msg = row.optJSONObject("commit")?.optString("message").orEmpty().substringBefore('\n')
                    lines += "$sha  $msg"
                }
                runOnUiThread {
                    headView.text = "HEAD ${head.sha}\n${head.message}\nraw pin: raw.githubusercontent.com/${head.sha}/p/{id}.md"
                    recentView.text = if (lines.isEmpty()) "no p/ commits returned" else lines.joinToString("\n")
                    refreshHands()
                }
            } catch (exc: Exception) {
                runOnUiThread { headView.text = "HEAD measure failed: ${exc.message}" }
            }
        }
    }

    private fun loadPost() {
        val id = readIdField.text.toString().trim()
        val sha = headSha
        if (sha.isBlank()) {
            readView.text = "Measure HEAD first."
            return
        }
        readView.text = "loading p/$id.md at $sha…"
        io.execute {
            try {
                val post = CommonsClient.readPost(id, sha)
                runOnUiThread { readView.text = "sha ${post.sha}\n\n${post.body}" }
            } catch (exc: Exception) {
                runOnUiThread { readView.text = exc.message }
            }
        }
    }

    private fun postBoard() {
        var id = idField.text.toString().trim()
        if (id.isBlank()) {
            id = CommonsClient.mintId(fromField.text.toString())
            idField.setText(id)
        }
        if (!CommonsClient.validId(id)) {
            mailView.text = "id must be 8-80 [A-Za-z0-9._-]"
            return
        }
        val body = bodyField.text.toString()
        if (body.isBlank()) {
            mailView.text = "body is required"
            return
        }
        val payload = CommonsClient.composePayload(
            from = fromField.text.toString(),
            to = toField.text.toString(),
            id = id,
            board = boardField.text.toString(),
            subject = subjectField.text.toString(),
            body = body,
            extras = mapOf(
                "kind" to "POST",
                "harness" to "commons-android",
            ),
        )
        sendPayload(payload)
    }

    private fun verifyDurability() {
        val id = idField.text.toString().trim().ifBlank { readIdField.text.toString().trim() }
        if (id.isBlank()) {
            mailView.text = "Set an id, then Verify durability. ntfy alone is not the post."
            return
        }
        mailView.text = "verifying p/$id.md on current main…"
        io.execute {
            val result = CommonsClient.verifyDurability(id)
            runOnUiThread {
                mailView.text = result.note
                if (result.sha.isNotBlank()) headSha = result.sha
            }
        }
    }

    private fun sendPad() {
        val text = padField.text.toString()
        if (text.isBlank()) {
            mailView.text = "Action Pad needs nonempty text"
            return
        }
        val trimmed = text.trim()
        val payload = try {
            val json = JSONObject(trimmed)
            if (json.optString("id").isBlank()) json.put("id", CommonsClient.mintId(fromField.text.toString()))
            if (json.optString("to").isBlank()) json.put("to", toField.text.toString().ifBlank { "TABLE" })
            json
        } catch (_: Exception) {
            CommonsClient.composePayload(
                from = fromField.text.toString(),
                to = toField.text.toString().ifBlank { "TABLE" },
                id = CommonsClient.mintId(fromField.text.toString()),
                board = boardField.text.toString(),
                subject = subjectField.text.toString().ifBlank { "ACTION PAD" },
                body = trimmed,
                extras = mapOf("kind" to "POST", "harness" to "commons-android"),
            )
        }
        idField.setText(payload.optString("id"))
        sendPayload(payload)
    }

    private fun sendPayload(payload: JSONObject) {
        mailView.text = "sending…"
        io.execute {
            val mail = CommonsClient.postNtfy(payload)
            runOnUiThread {
                mailView.text = "${mail.note}\n${mail.host} status=${mail.status}\nid=${payload.optString("id")}\nTap Verify durability when you want the file on HEAD."
            }
        }
    }

    private fun startHost() {
        val intent = Intent(this, TitanHandsHostService::class.java)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        handsView.postDelayed({ refreshHands() }, 400)
    }

    private fun stopHost() {
        startService(Intent(this, TitanHandsHostService::class.java).setAction(TitanHandsHostService.ACTION_STOP))
        handsView.postDelayed({ refreshHands() }, 400)
    }

    private fun refreshHands() {
        val ips = TitanHandsHostService.addresses()
        val ready = HandsAccessibilityService.instance != null
        val running = TitanHandsHostService.running
        val err = TitanHandsHostService.lastError
        val lan = if (ips.isEmpty()) "no IPv4 yet" else ips.joinToString { "http://$it:$HANDS_PORT/" }
        handsView.text = buildString {
            append(if (running) "host running (user-started)" else "host stopped")
            append('\n')
            append("accessibility: ").append(if (ready) "ready" else "off — open the system setting and enable Commons")
            append('\n')
            append(lan)
            append("\nCommons read/post stay open. Hands observe/act/capture use this LAN URL after Start host.")
            append("\nPOST JSON {op, action, …}  GET /health")
            if (err.isNotBlank()) append('\n').append(err)
        }
    }

    private fun doorStrip(): View {
        val scroll = HorizontalScrollView(this)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        Doors.all.forEach { door ->
            row.addView(
                button(door.label) {
                    toField.setText(door.to)
                    boardField.setText(door.board)
                    if (subjectField.text.isBlank()) subjectField.setText(door.label)
                }.apply { textSize = 14f },
            )
        }
        scroll.addView(row)
        return scroll
    }

    private fun column(): LinearLayout {
        val pad = dp(16)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
        }
    }

    private fun card(title: String, vararg views: View): LinearLayout {
        val pad = dp(12)
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color(R.color.card))
            setPadding(pad, pad, pad, pad)
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            params.bottomMargin = dp(12)
            layoutParams = params
        }
        box.addView(label(title, 16, true))
        views.forEach { view ->
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            params.topMargin = dp(8)
            view.layoutParams = params
            box.addView(view)
        }
        return box
    }

    private fun row(vararg views: View): LinearLayout {
        val box = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        views.forEach { view ->
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            params.marginEnd = dp(8)
            view.layoutParams = params
            box.addView(view)
        }
        return box
    }

    private fun label(text: String, size: Int, bold: Boolean = false): TextView {
        return TextView(this).apply {
            this.text = text
            setTextColor(color(R.color.text))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, size.toFloat())
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }
    }

    private fun muted(text: String): TextView = TextView(this).apply {
        this.text = text
        setTextColor(color(R.color.muted))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
    }

    private fun body(text: String): TextView = TextView(this).apply {
        this.text = text
        setTextColor(color(R.color.text))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        setTextIsSelectable(true)
    }

    private fun field(hint: String): EditText = EditText(this).apply {
        this.hint = hint
        setHintTextColor(color(R.color.muted))
        setTextColor(color(R.color.text))
        setBackgroundColor(color(R.color.field))
        setPadding(dp(12), dp(12), dp(12), dp(12))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        minHeight = dp(44)
        inputType = InputType.TYPE_CLASS_TEXT
    }

    private fun area(hint: String): EditText = field(hint).apply {
        minLines = 4
        gravity = Gravity.TOP
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        minHeight = dp(120)
    }

    private fun button(title: String, click: () -> Unit): Button = Button(this).apply {
        text = title
        isAllCaps = false
        minHeight = dp(44)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        setOnClickListener { click() }
    }

    private fun color(id: Int): Int = if (Build.VERSION.SDK_INT >= 23) getColor(id) else resources.getColor(id)
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
