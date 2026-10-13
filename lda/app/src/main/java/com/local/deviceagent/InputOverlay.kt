package com.local.deviceagent

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/**
 * A focusable TEXT-INPUT overlay for the agent's clarifying questions - the owner's "asking for
 * parameters (age/sex/criteria, …) should be an on-screen TEXT FIELD popup, not verbal". It floats
 * over the current task app (TYPE_APPLICATION_OVERLAY) so it doesn't disturb the foreground app, and
 * the soft keyboard works because the window is focusable. Mirrors the proven showInputBox pattern.
 * The owner can still answer by voice instead; whichever comes first wins.
 */
class InputOverlay {
    private var view: View? = null
    private var wm: WindowManager? = null

    @SuppressLint("ClickableViewAccessibility")
    fun show(context: Context, question: String, onSubmit: (String) -> Unit, onCancel: () -> Unit) {
        dismiss()
        val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        wm = windowManager
        val title = TextView(context).apply {
            text = question
            textSize = 15f; setTextColor(0xFFFFFFFF.toInt()); setPadding(8, 8, 8, 16)
        }
        val input = EditText(context).apply {
            hint = "Type your answer…"
            setBackgroundColor(0xFFFFFFFF.toInt())
            setTextColor(0xFF000000.toInt()); setHintTextColor(0xFF888888.toInt())
            setPadding(24, 24, 24, 24)
        }
        val sendBtn = Button(context).apply { text = "Send" }
        val closeBtn = Button(context).apply { text = "✕" }
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(input, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(sendBtn); addView(closeBtn)
        }
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xF0202020.toInt())
            setPadding(24, 24, 24, 24)
            addView(title); addView(row)
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL, // focusable (no NOT_FOCUSABLE) so the keyboard works
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM
            softInputMode = WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or
                WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
        }
        val submit = {
            val t = input.text.toString().trim()
            if (t.isNotEmpty()) { dismiss(); onSubmit(t) }
        }
        sendBtn.setOnClickListener { submit() }
        closeBtn.setOnClickListener { dismiss(); onCancel() }
        input.setOnEditorActionListener { _, _, _ -> submit(); true }
        view = root
        try { windowManager.addView(root, params); input.requestFocus() } catch (_: Exception) { view = null }
    }

    fun dismiss() {
        val v = view ?: return
        try { wm?.removeView(v) } catch (_: Exception) {}
        view = null
    }
}
