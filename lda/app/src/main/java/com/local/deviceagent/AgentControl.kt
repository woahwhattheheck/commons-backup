package com.local.deviceagent

import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * Shared power controls used by both the chat and menu screens, so the two buttons behave
 * identically everywhere.
 *
 *  - SLEEP: stop all active work (no tasks, no voice, model released from RAM/GPU) but KEEP
 *    passively learning - the accessibility service keeps quietly recording how you navigate.
 *  - EMERGENCY STOP: shut everything down, including the model and passive monitoring.
 *  - WAKE: bring the active agent back.
 */
object AgentControl {

    fun sleep(c: Context) {
        val s = SettingsManager(c)
        s.setPassiveLearningEnabled(true)
        ActionAccessibilityService.instance?.setPassiveLearning(true)
        s.setAgentEnabled(false)                                   // no tasks / no wake-word listening
        ActionAccessibilityService.instance?.haltInjection()       // KILL-SWITCH: halt injection SYNCHRONOUSLY here,
        // not later in the async onDestroy — the loop must not keep dispatching during the wind-down (ghost inputs).
        c.stopService(Intent(c, FloatingButtonService::class.java))
        c.stopService(Intent(c, AgentService::class.java))         // onDestroy releases the model
        AgentLog.log("power", "SLEEP — active agent off, model released, passive learning on")
    }

    fun emergencyStop(c: Context) {
        GauntletRunner.stop(c, "emergency stop")   // never let the benchmark relaunch tasks after a kill
        val s = SettingsManager(c)
        s.setPassiveLearningEnabled(false)
        ActionAccessibilityService.instance?.setPassiveLearning(false)
        s.setAgentEnabled(false)
        ActionAccessibilityService.instance?.haltInjection()       // KILL-SWITCH: synchronous input halt before teardown
        c.stopService(Intent(c, FloatingButtonService::class.java))
        c.stopService(Intent(c, AgentService::class.java))
        AgentLog.log("power", "EMERGENCY STOP — everything off, model shut down")
    }

    fun wake(c: Context) {
        SettingsManager(c).setAgentEnabled(true)
        try { c.startForegroundService(Intent(c, AgentService::class.java)) } catch (_: Exception) {}
        if (Settings.canDrawOverlays(c))
            try { c.startService(Intent(c, FloatingButtonService::class.java)) } catch (_: Exception) {}
        AgentLog.log("power", "WAKE — active agent on")
    }

    fun isActive(c: Context): Boolean = SettingsManager(c).isAgentEnabled()
}
