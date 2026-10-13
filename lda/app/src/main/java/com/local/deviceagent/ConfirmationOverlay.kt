package com.local.deviceagent

import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class ConfirmationOverlay {
    private var view: View? = null
    private var wm: WindowManager? = null

    fun show(context: Context, message: String, onYes: () -> Unit, onNo: () -> Unit) {
        dismiss()
        val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        wm = windowManager

        // GHOST-INPUT HARDENING (07-09): this used to be a full-screen MATCH_PARENT window that SWALLOWED every touch
        // (only Yes/No did anything) and rendered OVER the floating STOP button — so during a confirmation the owner's
        // touches "didn't register" and STOP was unreachable. Now the window WRAPS the card and carries
        // FLAG_NOT_TOUCH_MODAL, so touches OUTSIDE the card pass through to the app + the STOP overlay; only the card
        // is interactive. The dim still comes from FLAG_DIM_BEHIND (no full-screen touch-eating layer needed).
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(24, 24, 24, 24)
        }
        val card = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFF202020.toInt())
            setPadding(48, 48, 48, 48)
        }
        val title = TextView(context).apply {
            text = "Confirm action"
            textSize = 18f
            setTextColor(0xFFFFFFFF.toInt())
            setPadding(0, 0, 0, 16)
        }
        val msg = TextView(context).apply {
            text = message
            textSize = 15f
            setTextColor(0xFFDDDDDD.toInt())
            setPadding(0, 0, 0, 32)
        }
        val buttons = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        val no = Button(context).apply {
            text = "No, stop"
            setOnClickListener { onNo() }
        }
        val yes = Button(context).apply {
            text = "Yes, allow"
            setOnClickListener { onYes() }
        }
        buttons.addView(no)
        buttons.addView(yes)
        card.addView(title)
        card.addView(msg)
        card.addView(buttons)
        root.addView(card)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // NOT_TOUCH_MODAL: only the card (this window's bounds) captures touch; everything else passes through to
            // the app behind + the floating STOP button, so a confirmation can never trap the owner.
            WindowManager.LayoutParams.FLAG_DIM_BEHIND or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply { dimAmount = 0.5f; gravity = Gravity.CENTER }

        view = root
        try { windowManager.addView(root, params) } catch (_: Exception) {}
    }

    fun dismiss() {
        val v = view ?: return
        try { wm?.removeView(v) } catch (_: Exception) {}
        view = null
    }
}
