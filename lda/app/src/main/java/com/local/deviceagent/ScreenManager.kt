package com.local.deviceagent

import android.content.Context
import android.hardware.display.DisplayManager
import android.view.Display

class ScreenManager(private val context: Context) {
    private val displayManager = context.getSystemService(Context.DISPLAY_SERVICE) as DisplayManager

    fun getActiveDisplayId(): Int {
        val displays = displayManager.displays
        return displays.lastOrNull()?.displayId ?: Display.DEFAULT_DISPLAY
    }

    fun isDexConnected(): Boolean {
        return displayManager.displays.size > 1
    }

    fun getDisplayInfo(): String {
        return if (isDexConnected()) "DeX/External Mode" else "Foldable/Phone Mode"
    }
}
