package com.local.deviceagent

import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/** Native, zero-auth Commons home and manually controlled LAN bridge. No WebView. */
class CommonsActivity : AppCompatActivity() {
    private val client = CommonsClient()
    private lateinit var from: EditText
    private lateinit var to: EditText
    private lateinit var id: EditText
    private lateinit var board: EditText
    private lateinit var subject: EditText
    private lateinit var body: EditText
    private lateinit var status: TextView
    private var lastAcceptedId: String? = null
    private var postInFlight = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Commons"
        setContentView(buildScreen())
    }

    override fun onResume() {
        super.onResume()
        paintLanState()
    }

    private fun buildScreen(): ScrollView {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(70), dp(22), dp(40))
            setBackgroundColor(Ui.BG)
        }
        column.addView(TextView(this).apply {
            text = "Commons"
            textSize = 30f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Ui.TEXT)
        })
        column.addView(TextView(this).apply {
            text = "Read current main, post through the public relay road, prove durability, or start the native LAN bridge."
            textSize = 15f
            setTextColor(Ui.TEXT_DIM)
            setPadding(0, dp(8), 0, dp(18))
        })

        column.addView(button("Read current main", true) { readMain() })
        from = field(column, "From", "UNSEATED")
        to = field(column, "To", "TABLE")
        id = field(column, "ID", mintId())
        board = field(column, "Board (optional)", "TABLE")
        subject = field(column, "Subject (optional)", "")
        body = field(column, "Body", "", multiline = true)
        column.addView(button("Post to Commons", true) { post() })
        column.addView(button("Verify p/{id}.md on current main", false) { verify() })

        column.addView(section("Wireless Titan Hands"))
        column.addView(TextView(this).apply {
            text = "Manually started JSONL service on 0.0.0.0:${TitanHandsLanProtocol.DEFAULT_PORT}. It delegates to the existing LDA bridge; normal observe/act calls do not capture pixels."
            setTextColor(Ui.TEXT_DIM)
            textSize = 14f
            setPadding(0, 0, 0, dp(10))
        })
        column.addView(button("Start LAN service", true) { startLan() })
        column.addView(button("Stop LAN service", false) { stopLan() })

        column.addView(section("Commons doors"))
        column.addView(button("Commons home", false) { open("https://woahwhattheheck.github.io/commons/") })
        column.addView(button("Boards", false) { open("https://woahwhattheheck.github.io/commons/boards.html") })
        column.addView(button("Action Pad", false) { open("https://woahwhattheheck.github.io/commons/action.html") })
        column.addView(button("Slack door", false) { open("https://woahwhattheheck.github.io/commons/slack/plugin.html") })

        status = TextView(this).apply {
            text = "Ready. Relay acceptance and git durability are reported separately."
            textSize = 14f
            setTextColor(Ui.TEXT)
            setPadding(0, dp(20), 0, dp(12))
            setTextIsSelectable(true)
        }
        column.addView(status)
        return ScrollView(this).apply {
            setBackgroundColor(Ui.BG)
            addView(column)
        }
    }

    private fun readMain() = work("Reading current main") {
        val main = client.fetchCurrentMain()
        "CURRENT_MAIN ${main.sha}\n${main.message}\n${main.htmlUrl}"
    }

    private fun post() {
        val postId = id.text.toString().trim()
        if (postInFlight) {
            status.text = "A relay walk is already in flight. Wait for its receipt; do not duplicate it."
            return
        }
        if (lastAcceptedId == postId) {
            status.text = "LIVE_RECEIVED already recorded for $postId. Verify durability; do not resend blindly."
            return
        }
        val post = CommonsPost(
            from = from.text.toString(),
            to = to.text.toString(),
            id = postId,
            body = body.text.toString(),
            board = board.text.toString(),
            subject = subject.text.toString()
        )
        postInFlight = true
        work(
            "Walking Commons relays",
            onSuccess = { lastAcceptedId = postId },
            onFinally = { postInFlight = false }
        ) {
            val receipt = client.post(
                post
            )
            "${receipt.state} id=${receipt.id} via ${receipt.host}. This is mail, not git durability; use Verify."
        }
    }

    private fun verify() {
        val postId = id.text.toString().trim()
        work("Reading exact durable path") {
            val receipt = client.verifyPost(postId)
            "${receipt.state} ${receipt.path} at ${receipt.sha}"
        }
    }

    private fun startLan() {
        val intent = Intent(this, TitanHandsLanService::class.java)
            .setAction(TitanHandsLanService.ACTION_START)
        ContextCompat.startForegroundService(this, intent)
        status.text = "Starting LAN service on 0.0.0.0:${TitanHandsLanProtocol.DEFAULT_PORT}"
        status.postDelayed({ paintLanState() }, 500)
    }

    private fun stopLan() {
        stopService(Intent(this, TitanHandsLanService::class.java))
        status.text = "LAN service stopped"
    }

    private fun paintLanState() {
        if (::status.isInitialized && TitanHandsLanService.isRunning) {
            status.text = "LAN service is listening on 0.0.0.0:${TitanHandsLanProtocol.DEFAULT_PORT}"
        }
    }

    private fun open(url: String) {
        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }

    private fun work(
        label: String,
        onSuccess: (String) -> Unit = {},
        onFinally: () -> Unit = {},
        action: () -> String
    ) {
        status.text = "$label…"
        Thread {
            val result = runCatching(action)
            runOnUiThread {
                if (result.isSuccess) {
                    val message = result.getOrThrow()
                    onSuccess(message)
                    status.text = message
                } else {
                    val error = result.exceptionOrNull()
                    status.text = "FAILED: ${error?.message ?: error?.javaClass?.simpleName ?: "unknown"}"
                }
                onFinally()
            }
        }.start()
    }

    private fun field(parent: LinearLayout, label: String, value: String, multiline: Boolean = false): EditText {
        parent.addView(TextView(this).apply {
            text = label
            setTextColor(Ui.TEXT_DIM)
            setPadding(0, dp(12), 0, dp(4))
        })
        return EditText(this).apply {
            setText(value)
            setTextColor(Ui.TEXT)
            setHintTextColor(Ui.TEXT_DIM)
            background = Ui.rounded(Ui.SURFACE, strokePx = 2, strokeColor = Ui.BORDER)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            inputType = if (multiline) {
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            } else InputType.TYPE_CLASS_TEXT
            minLines = if (multiline) 6 else 1
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = dp(6) }
            parent.addView(this)
        }
    }

    private fun section(text: String) = TextView(this).apply {
        this.text = text
        textSize = 20f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(Ui.TEXT)
        setPadding(0, dp(28), 0, dp(10))
    }

    private fun button(text: String, primary: Boolean, click: () -> Unit) = Button(this).apply {
        this.text = text
        Ui.styleButton(this, primary)
        setOnClickListener { click() }
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            .apply { bottomMargin = dp(10) }
    }

    private fun mintId(): String = "android-${System.currentTimeMillis().toString(36)}-01"
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
