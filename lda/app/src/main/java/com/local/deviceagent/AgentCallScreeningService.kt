package com.local.deviceagent

import android.telecom.Call
import android.telecom.CallScreeningService

/**
 * Optionally auto-declines incoming calls, but ONLY when the user has turned on
 * "Auto-decline incoming calls" in Settings (default off, so calls ring normally
 * and are never silently missed).
 */
class AgentCallScreeningService : CallScreeningService() {
    override fun onScreenCall(callDetails: Call.Details) {
        val decline = try { SettingsManager(this).isAutoDeclineCalls() } catch (_: Exception) { false }
        respondToCall(
            callDetails,
            CallResponse.Builder()
                .setDisallowCall(decline)
                .setRejectCall(decline)
                .setSkipCallLog(false)
                .setSkipNotification(false)
                .build()
        )
    }
}
