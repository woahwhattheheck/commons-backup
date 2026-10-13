package com.local.deviceagent

import android.app.Activity
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView

/**
 * Shared MONOCHROME palette + small styling helpers (owner's call: black / white / grey and shades
 * only - no colored accent). Screens stay cohesive instead of each inventing its own colors.
 * Hierarchy is by BRIGHTNESS: a near-white "primary" reads as the accent, greys recede.
 */
object Ui {
    const val BG = 0xFF0D0E10.toInt()        // app background (near-black)
    const val SURFACE = 0xFF17181B.toInt()   // cards / secondary buttons (dark grey)
    const val BORDER = 0xFF2B2D31.toInt()    // hairline separators / button outlines
    const val ACCENT = 0xFFE8EAED.toInt()    // "primary": a near-white fill (no hue)
    const val ON_ACCENT = 0xFF0D0E10.toInt() // dark text on the light primary fill
    const val TEXT = 0xFFE8EAED.toInt()      // primary text (near-white)
    const val TEXT_DIM = 0xFF9AA0A6.toInt()  // secondary / captions (grey)
    const val SUCCESS = 0xFFE8EAED.toInt()   // ready / active = brightest
    const val WARNING = 0xFF9AA0A6.toInt()   // off / inactive = mid grey
    const val DANGER = 0xFFF2F3F5.toInt()    // stop = bright (meaning carried by the label + confirm)

    /** A solid, rounded background (optionally outlined) - the building block of the flat buttons. */
    fun rounded(color: Int, radiusPx: Float = 26f, strokePx: Int = 0, strokeColor: Int = BORDER): GradientDrawable =
        GradientDrawable().apply {
            setColor(color)
            cornerRadius = radiusPx
            if (strokePx > 0) setStroke(strokePx, strokeColor)
        }

    /** Style a button as PRIMARY (accent fill) or SECONDARY (surface + hairline outline): flat,
     *  rounded, sentence-case - a modern look instead of the raised grey default. */
    fun styleButton(b: Button, primary: Boolean) {
        b.background = if (primary) rounded(ACCENT) else rounded(SURFACE, strokePx = 2, strokeColor = BORDER)
        b.setTextColor(if (primary) ON_ACCENT else TEXT)
        b.setAllCaps(false)
        b.setPadding(40, 34, 40, 34)
        b.stateListAnimator = null   // drop the default elevation shadow for a flat surface
    }

    private const val BRAND_TAG = "brand_stamp"

    /** Overlay a small, dim ownership label in the bottom corner of an Activity's content (the owner
     *  wants it on every screen). Only on the agent's OWN screens - never an overlay on other apps -
     *  and non-interactive, so it never blocks the controls underneath. Idempotent. */
    fun stampBrand(activity: Activity) {
        val content = activity.findViewById<FrameLayout>(android.R.id.content) ?: return
        // Skip activities that do not set a content view.
        if (content.childCount == 0) return
        if (content.findViewWithTag<View>(BRAND_TAG) != null) return
        val label = TextView(activity).apply {
            tag = BRAND_TAG
            text = "Property of Bryce Muhlnickel"
            contentDescription = "Property of Bryce Muhlnickel"
            textSize = 9f
            setTextColor(0x73E6EDF3)   // ~45% opacity - "just there", not loud
            isClickable = false
            isFocusable = false
            setPadding(10, 4, 10, 4)
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.END
            ).apply { setMargins(0, 0, 18, 10) }
        }
        content.addView(label)
    }

    private const val BACK_TAG = "agent_back_btn"

    /** Add a small Back button to the top-left of every Activity. Samsung DeX (desktop windows) has
     *  NO system back button, so without this the owner can't navigate back inside the app. Harmless
     *  on a phone (system/gesture back still works). Idempotent; non-destructive (just onBack). */
    fun stampBackButton(activity: Activity) {
        val content = activity.findViewById<FrameLayout>(android.R.id.content) ?: return
        if (content.childCount == 0) return
        if (content.findViewWithTag<View>(BACK_TAG) != null) return
        val btn = TextView(activity).apply {
            tag = BACK_TAG
            text = "‹ Back"
            textSize = 13f
            setTextColor(TEXT)
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 999f; setColor(SURFACE); setStroke(2, BORDER)
            }
            isClickable = true
            setOnClickListener {
                try {
                    (activity as? androidx.activity.ComponentActivity)?.onBackPressedDispatcher?.onBackPressed()
                        ?: activity.finish()
                } catch (_: Exception) { activity.finish() }
            }
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP or Gravity.START
            ).apply { setMargins(16, 16, 0, 0) }
        }
        content.addView(btn)
    }
}
