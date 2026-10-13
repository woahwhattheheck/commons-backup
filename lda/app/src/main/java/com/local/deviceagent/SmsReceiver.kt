package com.local.deviceagent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.widget.Toast

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val triggerWord = SettingsManager(context).getTriggerWord()
        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)

        for (message in messages) {
            if (message.messageBody.contains(triggerWord, ignoreCase = true)) {
                Toast.makeText(
                    context,
                    "Agent activated by ${message.originatingAddress}",
                    Toast.LENGTH_LONG
                ).show()
                // Ensure the agent service is running
                context.startForegroundService(Intent(context, AgentService::class.java))
                return
            }
        }
    }
}
